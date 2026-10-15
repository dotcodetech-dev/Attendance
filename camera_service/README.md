# Aveon Camera Service

Standalone face-recognition attendance service. Watches an IP camera RTSP stream,
detects/recognizes faces (InsightFace), and posts punches to the Aveon backend.

## Setup

```
python -m venv venv          (use 64-bit Python 3.12)
venv\Scripts\pip install -r requirements.txt
```

Fill in the camera credentials in `.env` (CAMERA_HOST, CAMERA_USER, CAMERA_PASSWORD).

## Run

```
venv\Scripts\python -m uvicorn app.main:app --port 8100
```

- `GET /health` — service liveness
- `GET /status` — camera connection, model state, detection counters
- `POST /embed` — multipart photo upload → 512-d face embedding (used by enrollment)

First start downloads the InsightFace `buffalo_l` model (~300MB) to `~/.insightface`.

Phase 1: detections are logged to console only — no attendance is written yet.
