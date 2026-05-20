"""
alerts.py — /api/alerts routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..core.security import require_api_rate
from ..models.schemas import AlertSeverity
from ..services import liquidity_service as svc

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get(
    "",
    summary="List alerts, optionally filtered by severity",
)
async def get_alerts(
    request: Request,
    severity: str | None = Query(default=None, description="Filter: ok | warning | danger | info"),
    _rate: None = Depends(require_api_rate),
):
    if severity:
        allowed = {s.value for s in AlertSeverity}
        if severity not in allowed:
            raise HTTPException(400, f"Invalid severity. Allowed: {sorted(allowed)}")
    return {"alerts": svc.get_alerts(severity)}


@router.get(
    "/{alert_id}",
    summary="Get a single alert by ID",
)
async def get_alert(
    alert_id: str,
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    alerts = svc.get_alerts()
    alert  = next((a for a in alerts if a["id"] == alert_id), None)
    if not alert:
        raise HTTPException(404, f"Alert '{alert_id}' not found")
    return alert
