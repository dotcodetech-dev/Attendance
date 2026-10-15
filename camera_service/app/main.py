from __future__ import annotations
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, File, HTTPException, Response, UploadFile

from datetime import datetime

from .config import settings
from .debounce import PunchDebouncer
from .gallery import Gallery
from .poster import PunchPoster
from .recognizer import FaceRecognizer
from .stream import RTSPStream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("camera_service")

recognizer = FaceRecognizer()
stream = RTSPStream(settings.rtsp_url)
gallery = Gallery()
debouncer = PunchDebouncer()
poster = PunchPoster()

GALLERY_REFRESH_OK_S = 300  # re-sync every 5 min when healthy
GALLERY_REFRESH_FAIL_S = 30  # retry sooner while backend is unreachable
PUNCH_FLUSH_S = 5
HEARTBEAT_S = 60  # keep the virtual device "Online" (backend window is 300s)
STALL_RESTART_S = 600  # no frame this long -> exit; start-service.cmd relaunches us

state = {
    "model_error": None,
    "frames_processed": 0,
    "faces_detected_total": 0,
    "last_detection_ts": None,
    "worker_running": False,
    "matches_total": 0,
    "last_match": None,
    "last_punch": None,
    "last_near_miss": None,
    "near_misses_total": 0,
    "small_faces_skipped": 0,
    "auto_learned_total": 0,
}


def _post_autolearn(employee_code: str, embedding, det_score: float) -> None:
    """Feed a high-confidence live embedding back into the gallery."""
    try:
        resp = httpx.post(
            f"{settings.aveon_api_url}/face/auto-learn",
            json={
                "employee_code": employee_code,
                "embedding": embedding.tolist(),
                "det_score": det_score,
            },
            headers={"X-Service-Key": settings.service_api_key},
            timeout=15,
        )
        if resp.status_code == 200:
            state["auto_learned_total"] += 1
            gallery.try_refresh()
    except httpx.HTTPError as exc:
        logger.debug("Auto-learn post failed: %s", exc)


async def detection_worker() -> None:
    """Sample the latest frame every frame_interval_ms and log detections."""
    state["worker_running"] = True
    interval = settings.frame_interval_ms / 1000.0
    loop = asyncio.get_running_loop()
    last_log = 0.0
    try:
        while True:
            started = time.monotonic()
            frame = stream.latest()
            age = stream.frame_age_s
            if frame is not None and recognizer.loaded and age is not None and age < 2.0:
                faces = await loop.run_in_executor(None, recognizer.detect, frame)
                state["frames_processed"] += 1
                if faces:
                    state["faces_detected_total"] += len(faces)
                    state["last_detection_ts"] = time.time()
                    results = []
                    for f in faces:
                        face_h = f.bbox[3] - f.bbox[1]
                        if face_h < settings.min_face_px:
                            state["small_faces_skipped"] += 1
                            results.append(f"tiny face skipped ({face_h}px)")
                            continue
                        match, best, closest = gallery.match(f.embedding)
                        if match:
                            state["matches_total"] += 1
                            state["last_match"] = {
                                "employee_code": match.employee_code,
                                "employee_name": match.employee_name,
                                "similarity": round(match.similarity, 3),
                                "ts": time.time(),
                            }
                            results.append(
                                f"MATCH {match.employee_code} ({match.employee_name}) sim={match.similarity:.3f}"
                            )
                            if debouncer.observe(match.employee_code):
                                when = datetime.now()
                                poster.save_snapshot(frame, match.employee_code, when)
                                poster.enqueue(match.employee_code, match.similarity, when, frame)
                                state["last_punch"] = {
                                    "employee_code": match.employee_code,
                                    "employee_name": match.employee_name,
                                    "similarity": round(match.similarity, 3),
                                    "ts": when.isoformat(),
                                }
                                logger.info(
                                    "PUNCH confirmed: %s (%s) sim=%.3f",
                                    match.employee_code, match.employee_name, match.similarity,
                                )
                                if match.similarity >= settings.adapt_threshold:
                                    loop.run_in_executor(
                                        None, _post_autolearn,
                                        match.employee_code, f.embedding, f.score,
                                    )
                        else:
                            if best >= 0.25 and closest:
                                state["near_misses_total"] += 1
                                state["last_near_miss"] = {
                                    "closest_employee_code": closest,
                                    "similarity": round(best, 3),
                                    "ts": time.time(),
                                }
                            results.append(f"unknown (best sim={best:.3f} vs {closest}, det={f.score:.2f})")
                    # Throttle logging to once a second so a person standing
                    # in view doesn't flood the console at ~3 fps.
                    if time.monotonic() - last_log >= 1.0:
                        last_log = time.monotonic()
                        logger.info("%d face(s): %s", len(faces), "; ".join(results))
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.05, interval - elapsed))
    except asyncio.CancelledError:
        pass
    finally:
        state["worker_running"] = False


async def gallery_refresh_worker() -> None:
    """Keep the embedding gallery in sync with the backend."""
    loop = asyncio.get_running_loop()
    while True:
        ok = await loop.run_in_executor(None, gallery.try_refresh)
        await asyncio.sleep(GALLERY_REFRESH_OK_S if ok else GALLERY_REFRESH_FAIL_S)


async def punch_flush_worker() -> None:
    """Deliver queued punches to the backend, retrying failures."""
    loop = asyncio.get_running_loop()
    while True:
        if poster.pending:
            await loop.run_in_executor(None, poster.flush)
        await asyncio.sleep(PUNCH_FLUSH_S)


def _send_heartbeat() -> None:
    try:
        httpx.post(
            f"{settings.aveon_api_url}/face/heartbeat",
            json={
                "device_serial": settings.device_serial,
                "device_name": settings.device_name,
                "camera_connected": True,
            },
            headers={"X-Service-Key": settings.service_api_key},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.debug("Heartbeat failed: %s", exc)


async def heartbeat_worker() -> None:
    """While the camera stream is up, tell the backend so the Devices page
    shows the virtual camera device as Online."""
    loop = asyncio.get_running_loop()
    while True:
        if stream.connected:
            await loop.run_in_executor(None, _send_heartbeat)
        await asyncio.sleep(HEARTBEAT_S)


async def stall_watchdog() -> None:
    """Self-heal for a wedged capture: an FFmpeg session inside a long-running
    process can keep timing out even after a camera outage ends, while a fresh
    process reconnects immediately. If no frame has arrived for STALL_RESTART_S,
    exit the process — start-service.cmd relaunches it within 10s."""
    started = time.monotonic()
    while True:
        await asyncio.sleep(30)
        age = stream.frame_age_s
        alive_s = time.monotonic() - started
        never_connected = age is None and alive_s > STALL_RESTART_S
        gone_stale = age is not None and age > STALL_RESTART_S
        if never_connected or gone_stale:
            logger.critical(
                "No camera frame for over %d min — exiting so the launcher "
                "restarts a fresh process", STALL_RESTART_S // 60,
            )
            os._exit(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, recognizer.load)
    except Exception as exc:  # noqa: BLE001
        state["model_error"] = str(exc)
        logger.exception("Failed to load InsightFace model")

    gallery_task = asyncio.create_task(gallery_refresh_worker())
    punch_task = asyncio.create_task(punch_flush_worker())
    heartbeat_task = asyncio.create_task(heartbeat_worker())

    worker_task = None
    watchdog_task = None
    if settings.camera_configured:
        logger.info("Connecting to camera: %s", settings.rtsp_url_masked)
        stream.start()
        worker_task = asyncio.create_task(detection_worker())
        watchdog_task = asyncio.create_task(stall_watchdog())
    else:
        logger.warning("Camera not configured — set CAMERA_HOST/CAMERA_USER/CAMERA_PASSWORD in .env. "
                       "Service is up for /health and /embed only.")

    yield

    gallery_task.cancel()
    punch_task.cancel()
    heartbeat_task.cancel()
    if worker_task:
        worker_task.cancel()
    if watchdog_task:
        watchdog_task.cancel()
    stream.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    age = stream.frame_age_s
    return {
        "camera_configured": settings.camera_configured,
        "camera_connected": stream.connected,
        "last_frame_age_s": round(age, 2) if age is not None else None,
        "reconnect_count": stream.reconnect_count,
        "model_loaded": recognizer.loaded,
        "model_error": state["model_error"],
        "worker_running": state["worker_running"],
        "frames_processed": state["frames_processed"],
        "faces_detected_total": state["faces_detected_total"],
        "last_detection_ts": state["last_detection_ts"],
        "gallery_size": gallery.size,
        "gallery_last_sync_ts": gallery.last_sync_ts,
        "gallery_last_sync_error": gallery.last_sync_error,
        "match_threshold": settings.match_threshold,
        "match_soft_threshold": settings.match_soft_threshold,
        "match_margin": settings.match_margin,
        "matches_total": state["matches_total"],
        "last_match": state["last_match"],
        "last_punch": state["last_punch"],
        "last_near_miss": state["last_near_miss"],
        "near_misses_total": state["near_misses_total"],
        "small_faces_skipped": state["small_faces_skipped"],
        "auto_learned_total": state["auto_learned_total"],
        "punches_posted": poster.posted_total,
        "punches_pending": poster.pending,
        "punch_post_error": poster.failed_last_error,
    }


@app.post("/gallery/refresh")
async def refresh_gallery():
    """Force an immediate gallery re-sync (called after enrolling someone)."""
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, gallery.try_refresh)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Gallery sync failed: {gallery.last_sync_error}")
    return {"synced": gallery.size}


@app.get("/frame")
def frame():
    """Current camera frame as JPEG (used by enroll-from-camera)."""
    f = stream.latest()
    age = stream.frame_age_s
    if f is None or age is None or age > 5.0:
        raise HTTPException(status_code=503, detail="No live camera frame available")
    ok, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise HTTPException(status_code=500, detail="Frame encode failed")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.post("/embed")
async def embed(photo: UploadFile = File(...)):
    """Return face embedding(s) for an uploaded photo (used by enrollment)."""
    if not recognizer.loaded:
        raise HTTPException(status_code=503, detail=f"Model not loaded: {state['model_error']}")
    data = await photo.read()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image")
    loop = asyncio.get_running_loop()
    faces = await loop.run_in_executor(None, recognizer.detect, image)
    if not faces:
        raise HTTPException(status_code=422, detail="No face found in photo")
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    best = faces[0]
    return {
        "face_count": len(faces),
        "det_score": best.score,
        "bbox": best.bbox,
        "embedding": best.embedding.tolist(),
    }
