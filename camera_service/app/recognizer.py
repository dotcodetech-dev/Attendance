from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from .config import settings

logger = logging.getLogger("camera_service.recognizer")


@dataclass
class DetectedFace:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    score: float
    embedding: np.ndarray  # 512-d, L2-normalized


class FaceRecognizer:
    """InsightFace buffalo_l: detection + 512-d embedding, CPU by default."""

    def __init__(self) -> None:
        self._app = None

    @property
    def loaded(self) -> bool:
        return self._app is not None

    def load(self) -> None:
        # Import here so the service can still boot (and report a clear
        # /status error) if the model download or native deps fail.
        from insightface.app import FaceAnalysis

        logger.info("Loading InsightFace model (first run downloads ~300MB)...")
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        # det_thresh 0.4 (default 0.5): keeps the angled/motion-blurred faces a
        # walking person produces; weak detections are filtered by min_face_px
        # and the vote confirmation instead.
        app.prepare(
            ctx_id=settings.ctx_id,
            det_size=(settings.detector_size, settings.detector_size),
            det_thresh=0.4,
        )
        self._app = app
        logger.info("InsightFace model ready")

    def detect(self, frame_bgr: np.ndarray) -> List[DetectedFace]:
        if self._app is None:
            raise RuntimeError("Recognizer not loaded")
        faces = self._app.get(frame_bgr)
        pad = 0
        if not faces:
            # SCRFD misses faces that nearly fill the frame (typical for
            # tightly-cropped enrollment photos); retry with a border.
            pad = int(min(frame_bgr.shape[:2]) * 0.4)
            padded = cv2.copyMakeBorder(
                frame_bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(114, 114, 114)
            )
            faces = self._app.get(padded)
        results: List[DetectedFace] = []
        for face in faces:
            embedding = face.normed_embedding
            if embedding is None:
                continue
            x1, y1, x2, y2 = (int(v) - pad for v in face.bbox)
            results.append(
                DetectedFace(bbox=(x1, y1, x2, y2), score=float(face.det_score), embedding=embedding)
            )
        return results
