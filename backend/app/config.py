from __future__ import annotations
from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Biometric Device Management API"
    # White-label brand: default organisation name shown in the sidebar / report
    # headers until the client sets their own under Configuration -> Organization.
    brand_name: str = "Aveon"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "replace_this_with_a_strong_secret"
    access_token_expire_minutes: int = 480
    admin_username: str = "admin"
    admin_password: str = "admin123"

    sqlserver_host: str = "localhost"
    sqlserver_port: int = 1433
    sqlserver_server: Optional[str] = None
    sqlserver_database: str = "BiometricServer"
    sqlserver_user: str = "sa"
    sqlserver_password: str = "YourStrong!Passw0rd"
    sqlserver_driver: str = "ODBC Driver 18 for SQL Server"
    sqlserver_encrypt: str = "no"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    webhook_url: Optional[str] = None

    # Face-recognition camera service (camera_service/). The API key is a shared
    # secret: camera_service sends it in X-Service-Key when pulling the gallery.
    camera_service_url: str = "http://localhost:8100"
    camera_service_api_key: str = "change_me_shared_secret"

    # Attendance export (mirrors eTimeTrackLite's WebScheduler CSV/FTP export).
    attendance_export_enabled: bool = False
    attendance_export_separator: str = ","          # "," or "\t" or "|"
    attendance_export_extension: str = "csv"
    attendance_export_prefix: str = "attendance_"
    attendance_export_folder: Optional[str] = None  # local folder to write into
    attendance_export_ftp_host: Optional[str] = None
    attendance_export_ftp_port: int = 21
    attendance_export_ftp_user: Optional[str] = None
    attendance_export_ftp_password: Optional[str] = None
    attendance_export_ftp_dir: str = "/"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlalchemy_database_uri(self) -> str:
        server = self.sqlserver_server or f"{self.sqlserver_host},{self.sqlserver_port}"
        odbc_connect = (
            f"DRIVER={{{self.sqlserver_driver}}};"
            f"SERVER={server};"
            f"DATABASE={self.sqlserver_database};"
            f"UID={self.sqlserver_user};"
            f"PWD={self.sqlserver_password};"
            f"TrustServerCertificate=yes;"
            f"Encrypt={self.sqlserver_encrypt};"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_connect)}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
