"""
security.py — Security utilities.
Rate limiting, CORS config, input sanitization, API key auth.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from typing import Callable

# ── CORS origins (update for production) ──────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # add your production domain here, e.g. "https://liquidity.yourcompany.com"
]

ALLOWED_METHODS: list[str] = ["GET", "POST"]
ALLOWED_HEADERS: list[str] = ["Content-Type", "Authorization", "X-API-Key"]


@dataclass(frozen=True)
class CorsConfig:
    allow_origins: list[str]
    allow_methods: list[str]
    allow_headers: list[str]
    allow_credentials: bool = True


CORS = CorsConfig(
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
    allow_credentials=True,
)


# ── In-memory rate limiter ─────────────────────────────────────────────────────
# Per-IP sliding window.  Not suitable for multi-process deployments —
# swap for Redis/slowapi in production.


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._log: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._log[key]
        # evict expired timestamps
        cutoff = now - self.window
        self._log[key] = [t for t in hits if t > cutoff]
        if len(self._log[key]) >= self.max_calls:
            return False
        self._log[key].append(now)
        return True


# Global limiters
_api_limiter = RateLimiter(max_calls=60, window_seconds=60)  # 60 req/min per IP
_search_limiter = RateLimiter(max_calls=30, window_seconds=60)  # 30 searches/min
_opt_limiter = RateLimiter(max_calls=10, window_seconds=60)  # 10 optimise/min


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_api_rate(request: Request) -> None:
    ip = get_client_ip(request)
    if not _api_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
        )


def require_search_rate(request: Request) -> None:
    ip = get_client_ip(request)
    if not _search_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Search rate limit exceeded.",
        )


def require_opt_rate(request: Request) -> None:
    ip = get_client_ip(request)
    if not _opt_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Optimization rate limit exceeded.",
        )


# ── Input sanitization ─────────────────────────────────────────────────────────
_DANGEROUS = re.compile(r"[<>\"'%;()&+]")


def sanitize_string(value: str, max_len: int = 200) -> str:
    """Strip dangerous chars and truncate. Raises 400 on injection attempt."""
    if _DANGEROUS.search(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid characters in input.",
        )
    return value[:max_len].strip()


# ── Security headers middleware ────────────────────────────────────────────────
async def security_headers_middleware(request: Request, call_next: Callable):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response
