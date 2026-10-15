from __future__ import annotations
import mimetypes
import os

import logging

# Windows' type registry often lacks .webp, so the logo was served as application/octet-stream.
mimetypes.add_type("image/webp", ".webp")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.database import ensure_compat_schema, get_engine
from app.iclock.routes import iclock_router

log = logging.getLogger(__name__)

# Built React frontend (frontend/dist), served so the whole app is reachable on
# one origin/port through the IIS proxy. Path: backend/app/main.py -> ../../frontend/dist
_FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)


class IclockPathNormalizeMiddleware:
    """
    Real eSSL/ZKTeco firmwares call the push endpoints with different suffixes
    depending on model — /iclock/cdata, /iclock/cdata.aspx or /iclock/cdata.php
    (confirmed against the production eBioServer url-mappings). FastAPI only
    registers the bare paths, so without this a remote device whose firmware
    appends a suffix would get 404 on every request and never sync.

    This raw-ASGI middleware strips a trailing .aspx/.php from any /iclock/*
    path before routing. It rewrites only the path (never the body), so large
    ATTLOG/photo POSTs stream through untouched.
    """

    _SUFFIXES = (".aspx", ".php")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/iclock/"):
                for suffix in self._SUFFIXES:
                    if path.endswith(suffix):
                        new_path = path[: -len(suffix)]
                        scope = dict(scope)
                        scope["path"] = new_path
                        raw = scope.get("raw_path")
                        if raw:
                            # raw_path includes the query string; rewrite only the path part.
                            q_index = raw.find(b"?")
                            if q_index == -1:
                                scope["raw_path"] = new_path.encode("ascii", "ignore")
                            else:
                                scope["raw_path"] = (
                                    new_path.encode("ascii", "ignore") + raw[q_index:]
                                )
                        break
        await self.app(scope, receive, send)


class ApiGzipMiddleware:
    """Compress the JSON API (the Employees list is ~400 KB uncompressed and the Users list ~100 KB; over a slow
    link that was seconds of waiting). Only /api/ is compressed - the readers' /iclock/ traffic is left untouched."""

    def __init__(self, app) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/"):
            await self._gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


app = FastAPI(title=settings.app_name)
app.add_middleware(IclockPathNormalizeMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"^https?://((localhost|127\.0\.0\.1)|(\d{1,3}\.){3}\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiGzipMiddleware)

@app.get("/health")
def health() -> dict:
    db_ok = False
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        log.warning("Health check DB probe failed: %s", exc)
    status = "ok" if db_ok else "degraded"
    result = {"status": status, "database": "connected" if db_ok else "unreachable"}
    if not db_ok:
        return JSONResponse(status_code=503, content=result)
    return result


@app.on_event("startup")
def startup_checks() -> None:
    try:
        ensure_compat_schema()
    except Exception:
        # Keep API available in bootstrap mode even when DB isn't ready.
        pass

app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(iclock_router, prefix="/iclock", tags=["iclock"])


# --- Serve the built frontend (registered LAST so it never shadows the API) ---
if os.path.isdir(_FRONTEND_DIST):
    # Hashed build assets (JS/CSS/images).
    _assets_dir = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")
    _branding_dir = os.path.join(_FRONTEND_DIST, "branding")
    if os.path.isdir(_branding_dir):
        app.mount("/branding", StaticFiles(directory=_branding_dir), name="branding")

    _index_html = os.path.join(_FRONTEND_DIST, "index.html")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # API/iclock/health are matched earlier; anything else is the SPA.
        # Real files under dist (favicon, logo, etc.) are served directly;
        # unknown paths return index.html so client-side routing works.
        if full_path:
            candidate = os.path.normpath(os.path.join(_FRONTEND_DIST, full_path))
            if candidate.startswith(_FRONTEND_DIST) and os.path.isfile(candidate):
                return FileResponse(candidate)
        if os.path.isfile(_index_html):
            return FileResponse(_index_html)
        return JSONResponse({"detail": "Frontend not built"}, status_code=404)
