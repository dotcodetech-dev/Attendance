from __future__ import annotations
from functools import lru_cache
from typing import Optional
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Aveon Camera Service"

    # Camera connection — either set camera_rtsp_url directly, or the parts below.
    camera_rtsp_url: Optional[str] = None
    camera_scheme: str = "rtsp"  # "rtsps" for cameras in TLS-only mode (e.g. CP Plus secure mode)
    camera_host: str = "CAMERA_IP_HERE"
    camera_port: int = 554
    camera_user: str = "CAMERA_USERNAME_HERE"
    camera_password: str = "CAMERA_PASSWORD_HERE"
    camera_stream_path: str = "/Streaming/Channels/102"

    service_port: int = 8100
    frame_interval_ms: int = 300

    # Identity of the virtual attendance device this camera punches under.
    device_serial: str = "CAM-ENTRY-01"
    device_name: str = "Entry Camera"

    aveon_api_url: str = "http://localhost:8000/api/v1"
    service_api_key: str = "change_me_shared_secret"

    # --- Matching ---
    # Hard accept: similarity alone is enough.
    match_threshold: float = 0.5
    # Soft accept: similarity >= soft threshold AND the runner-up person is at
    # least match_margin behind (a confident, unambiguous borderline match).
    match_soft_threshold: float = 0.40
    match_margin: float = 0.12
    # Faces with a bounding box shorter than this (pixels) are too small for a
    # reliable embedding — detected but not matched.
    min_face_px: int = 48

    # --- Punch confirmation ---
    # A punch fires after `consecutive_frames` matched frames (votes) within
    # `vote_window_s` seconds — tolerant of gaps while someone walks past.
    consecutive_frames: int = 2
    vote_window_s: float = 5.0
    debounce_minutes: int = 5

    # --- Auto-learning (template adaptation) ---
    # Confirmed punches at/above this similarity are fed back into the gallery
    # (Source=AutoLearn, capped per person server-side), so the gallery adapts
    # to the camera's angle and lighting over time.
    adapt_threshold: float = 0.60

    snapshot_dir: str = "snapshots"
    # -1 = CPU. Set to a GPU id if onnxruntime-gpu is installed later.
    ctx_id: int = -1
    detector_size: int = 640

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def rtsp_url(self) -> str:
        if self.camera_rtsp_url:
            return self.camera_rtsp_url
        user = quote(self.camera_user, safe="")
        password = quote(self.camera_password, safe="")
        return f"{self.camera_scheme}://{user}:{password}@{self.camera_host}:{self.camera_port}{self.camera_stream_path}"

    @property
    def rtsp_url_masked(self) -> str:
        return self.rtsp_url.replace(quote(self.camera_password, safe=""), "*****").replace(
            self.camera_password, "*****"
        )

    @property
    def camera_configured(self) -> bool:
        if self.camera_rtsp_url:
            return True
        return "CAMERA_IP_HERE" not in self.camera_host


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
