from __future__ import annotations
import logging
import os
import threading
import time
from typing import Optional

# Must be set before the first VideoCapture: force TCP transport and a socket
# timeout so a dead camera fails fast instead of hanging the reader thread.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|timeout;10000000")

import cv2
import numpy as np

logger = logging.getLogger("camera_service.stream")


class RTSPStream:
    """Background reader for an RTSP camera with automatic reconnect.

    Continuously drains the stream (so frames never back up in the buffer)
    and keeps only the most recent frame; consumers sample it at their own
    pace via latest().
    """

    RECONNECT_BACKOFF_S = (2, 5, 10, 30)

    def __init__(self, url: str) -> None:
        self._url = url
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._frame_ts: float = 0.0
        self._connected = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.reconnect_count = 0

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rtsp-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    # -- consumer API --------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def frame_age_s(self) -> Optional[float]:
        if self._frame_ts == 0.0:
            return None
        return time.monotonic() - self._frame_ts

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    # -- reader thread -------------------------------------------------

    def _run(self) -> None:
        backoff_idx = 0
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                self._connected = False
                delay = self.RECONNECT_BACKOFF_S[min(backoff_idx, len(self.RECONNECT_BACKOFF_S) - 1)]
                logger.warning("Camera connect failed, retrying in %ss", delay)
                backoff_idx += 1
                self.reconnect_count += 1
                if self._stop.wait(delay):
                    return
                continue

            logger.info("Camera connected")
            self._connected = True
            backoff_idx = 0

            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.warning("Frame read failed, reconnecting")
                    break
                with self._lock:
                    self._frame = frame
                    self._frame_ts = time.monotonic()

            cap.release()
            self._connected = False
            self.reconnect_count += 1
        self._connected = False
