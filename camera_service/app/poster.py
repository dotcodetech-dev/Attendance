from __future__ import annotations

import base64
import logging
import os
import threading
from collections import deque
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

import httpx

from .config import settings

logger = logging.getLogger("camera_service.poster")


class PunchPoster:
    """Posts confirmed punches to the Aveon backend, with snapshot audit trail.

    Failed posts stay queued and are retried by the flush worker; the backend
    dedupes within a minute window, so a retry after a timeout is safe.
    """

    MAX_QUEUE = 500

    def __init__(self) -> None:
        self._queue: deque[dict] = deque(maxlen=self.MAX_QUEUE)
        self._lock = threading.Lock()
        self.posted_total = 0
        self.failed_last_error: Optional[str] = None

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def save_snapshot(self, frame_bgr: np.ndarray, employee_code: str, when: datetime) -> Optional[str]:
        """Write the punch frame under snapshots/YYYY-MM-DD/; returns the path."""
        try:
            day_dir = os.path.join(settings.snapshot_dir, when.strftime("%Y-%m-%d"))
            os.makedirs(day_dir, exist_ok=True)
            path = os.path.join(day_dir, f"{employee_code}_{when.strftime('%H%M%S')}.jpg")
            cv2.imwrite(path, frame_bgr)
            return path
        except Exception as exc:  # noqa: BLE001
            logger.warning("Snapshot save failed: %s", exc)
            return None

    def enqueue(self, employee_code: str, similarity: float, when: datetime,
                frame_bgr: Optional[np.ndarray] = None) -> None:
        snapshot_b64 = None
        if frame_bgr is not None:
            ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                snapshot_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        punch = {
            "employee_code": employee_code,
            "timestamp": when.isoformat(),
            "similarity": similarity,
            "device_serial": settings.device_serial,
            "device_name": settings.device_name,
            "snapshot_b64": snapshot_b64,
        }
        with self._lock:
            self._queue.append(punch)

    def flush(self) -> None:
        """Post queued punches in order; stop at the first failure (retry later)."""
        while True:
            with self._lock:
                if not self._queue:
                    return
                punch = self._queue[0]
            try:
                resp = httpx.post(
                    f"{settings.aveon_api_url}/face/punch",
                    json=punch,
                    headers={"X-Service-Key": settings.service_api_key},
                    timeout=30,
                )
            except httpx.HTTPError as exc:
                self.failed_last_error = f"{exc.__class__.__name__}: {exc}"
                logger.warning("Punch post failed (will retry): %s", self.failed_last_error)
                return
            if resp.status_code == 200:
                body = resp.json()
                self.posted_total += 1
                self.failed_last_error = None
                logger.info(
                    "Punch stored: %s at %s%s",
                    punch["employee_code"], punch["timestamp"],
                    " (duplicate)" if body.get("duplicate") else "",
                )
            elif resp.status_code == 404:
                # Employee vanished between match and post — drop, don't wedge the queue.
                logger.warning("Punch for %s rejected: %s", punch["employee_code"], resp.text)
            else:
                self.failed_last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning("Punch post failed (will retry): %s", self.failed_last_error)
                return
            with self._lock:
                if self._queue and self._queue[0] is punch:
                    self._queue.popleft()
