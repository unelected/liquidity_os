"""
main.py — FastAPI application entry point.

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

The app also serves the frontend from /frontend when run directly.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.security import CORS, security_headers_middleware
from backend.routers import alerts, dashboard, optimization, search

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("liquidity_os")

# ── App factory ────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
FRONTEND_DIR  = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LiquidityOS backend starting up…")
    yield
    logger.info("LiquidityOS backend shutting down.")


app = FastAPI(
    title       = "LiquidityOS API",
    description = "Predictive liquidity management for fintech. "
                  "All endpoints return JSON. Seed data is used when no DB is connected.",
    version     = "1.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS.allow_origins,
    allow_credentials=CORS.allow_credentials,
    allow_methods=CORS.allow_methods,
    allow_headers=CORS.allow_headers,
)
app.middleware("http")(security_headers_middleware)


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )


# ── API routers ────────────────────────────────────────────────────────────────
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(optimization.router)
app.include_router(search.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"], summary="Health check")
async def health():
    return {"status": "ok", "version": app.version}


# ── Frontend static files ──────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Frontend not found. Run from project root."}, status_code=404)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def catch_all(full_path: str):
        """Serve frontend SPA for any non-API path."""
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # SPA fallback
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Not found"}, status_code=404)
