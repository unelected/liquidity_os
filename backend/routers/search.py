"""
search.py — /api/search route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.params import Query as FastQuery

from ..core.security import require_search_rate, sanitize_string
from ..models.schemas import SearchResponse, SearchResult
from ..services import liquidity_service as svc

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Full-text search across accounts, alerts, scenarios",
)
async def search(
    request: Request,
    q: str = str(FastQuery(min_length=1, max_length=100, description="Search query")),
    _rate: None = Depends(require_search_rate),
):
    clean_q = sanitize_string(q, max_len=100)
    results = svc.search(clean_q)
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )
