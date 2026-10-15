from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import numpy as np

from .config import settings

logger = logging.getLogger("camera_service.gallery")


@dataclass
class Match:
    employee_code: str
    employee_name: str
    similarity: float
    embedding_id: int


class Gallery:
    """Employee embeddings pulled from the Aveon backend, cached in memory.

    Embeddings are L2-normalized on both sides, so cosine similarity is a
    plain dot product against the (N, 512) matrix.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._matrix: Optional[np.ndarray] = None
        self._meta: list[dict] = []  # parallel to matrix rows
        # Per-person template fusion: row indices and centroid per person.
        self._persons: list[dict] = []  # {employee_code, employee_name}
        self._person_rows: list[np.ndarray] = []
        self._centroids: Optional[np.ndarray] = None  # (P, 512)
        self.last_sync_ts: Optional[float] = None
        self.last_sync_error: Optional[str] = None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._meta)

    def refresh(self) -> int:
        """Pull the full gallery from the backend. Returns entry count."""
        url = f"{settings.aveon_api_url}/face/gallery"
        resp = httpx.get(url, headers={"X-Service-Key": settings.service_api_key}, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        entries = payload.get("entries", [])

        meta = []
        vectors = []
        for e in entries:
            vec = np.asarray(e["embedding"], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm == 0 or vec.shape[0] != 512:
                continue
            vectors.append(vec / norm)
            meta.append(
                {
                    "employee_code": e["employee_code"],
                    "employee_name": e["employee_name"],
                    "embedding_id": e["embedding_id"],
                }
            )

        matrix = np.vstack(vectors) if vectors else None

        # Group rows by person and build a normalized centroid per person —
        # fused templates generalize across pose/lighting better than any
        # single enrollment photo.
        persons: list[dict] = []
        person_rows: list[np.ndarray] = []
        centroids = None
        if matrix is not None:
            by_code: dict[str, list[int]] = {}
            for i, m in enumerate(meta):
                by_code.setdefault(m["employee_code"], []).append(i)
            cent_vecs = []
            for code, idxs in by_code.items():
                persons.append({
                    "employee_code": code,
                    "employee_name": meta[idxs[0]]["employee_name"],
                })
                person_rows.append(np.asarray(idxs, dtype=np.int64))
                c = matrix[idxs].mean(axis=0)
                cent_vecs.append(c / (np.linalg.norm(c) or 1.0))
            centroids = np.vstack(cent_vecs)

        with self._lock:
            self._matrix = matrix
            self._meta = meta
            self._persons = persons
            self._person_rows = person_rows
            self._centroids = centroids
            self.last_sync_ts = time.time()
            self.last_sync_error = None
        logger.info("Gallery synced: %d embedding(s), %d person(s)", len(meta), len(persons))
        return len(meta)

    def try_refresh(self) -> bool:
        try:
            self.refresh()
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_sync_error = f"{exc.__class__.__name__}: {exc}"
            logger.warning("Gallery sync failed: %s", self.last_sync_error)
            return False

    def match(self, embedding: np.ndarray) -> tuple[Optional[Match], float, Optional[str]]:
        """Best gallery match for a normalized embedding.

        Per person, the score is max(best individual photo, fused centroid).
        Acceptance is two-tier:
          - hard: score >= match_threshold, or
          - soft: score >= match_soft_threshold AND the runner-up person is at
            least match_margin behind (unambiguous borderline match).

        Returns (match, best_similarity, closest_employee_code) — the last two
        are reported even when no match is accepted, for tuning.
        """
        with self._lock:
            matrix = self._matrix
            meta = self._meta
            persons = self._persons
            person_rows = self._person_rows
            centroids = self._centroids
        if matrix is None or not persons:
            return None, 0.0, None

        e = embedding.astype(np.float32)
        sims = matrix @ e
        cent_sims = centroids @ e

        scores = np.empty(len(persons), dtype=np.float32)
        for p, rows in enumerate(person_rows):
            scores[p] = max(float(sims[rows].max()), float(cent_sims[p]))

        order = np.argsort(scores)[::-1]
        p1 = int(order[0])
        s1 = float(scores[p1])
        s2 = float(scores[int(order[1])]) if len(order) > 1 else 0.0
        code1 = persons[p1]["employee_code"]

        accepted = s1 >= settings.match_threshold or (
            s1 >= settings.match_soft_threshold and (s1 - s2) >= settings.match_margin
        )
        if not accepted:
            return None, s1, code1

        rows = person_rows[p1]
        best_row = int(rows[int(np.argmax(sims[rows]))])
        return (
            Match(code1, persons[p1]["employee_name"], s1, meta[best_row]["embedding_id"]),
            s1,
            code1,
        )
