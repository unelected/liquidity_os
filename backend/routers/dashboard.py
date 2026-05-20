"""
dashboard.py — /api/dashboard and /api/accounts routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..core.security import require_api_rate
from ..models.schemas import AccountStatus, DashboardResponse
from ..services import liquidity_service as svc

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Full dashboard payload",
)
async def get_dashboard(
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    """
    Returns all data needed to render the dashboard:
    summary stats, accounts, alerts, cashflow, forecast,
    clearing delays, optimization plan, stress scenarios.
    """
    return svc.get_dashboard()


@router.get(
    "/accounts",
    summary="List nostro accounts, optionally filtered by status",
)
async def get_accounts(
    request: Request,
    status: str | None = Query(
        default=None, description="Filter: ok | warning | danger"
    ),
    _rate: None = Depends(require_api_rate),
):
    if status:
        # Validate against enum without raising a 422 (friendlier message)
        allowed = {s.value for s in AccountStatus}
        if status not in allowed:
            from fastapi import HTTPException

            raise HTTPException(400, f"Invalid status. Allowed: {sorted(allowed)}")
    return {"accounts": svc.get_accounts(status)}


@router.get(
    "/cashflow/anomalies",
    summary="Z-score anomaly detection on the cashflow series",
)
async def cashflow_anomalies(
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    data = svc.get_dashboard()
    anomalies = svc.detect_cashflow_anomalies(data["cashflow"])
    return {"anomalies": anomalies, "count": len(anomalies)}
