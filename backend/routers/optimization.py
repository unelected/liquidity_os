"""
optimization.py — /api/optimize, /api/rebalance, /api/reserve,
                  /api/settlement, /api/intraday, /api/simulate
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..core.security import require_opt_rate, require_api_rate
from ..models.schemas import (
    OptimizeRequest, OptimizeResponse, ScenarioKey, ScenarioRequest,
)
from ..services import liquidity_service as svc
from ..services.optimization_engine import (
    compute_reserve_optimization,
    forecast_settlement_delays,
    forecast_intraday,
    compute_rebalancing,
    simulate_scenario,
)

router = APIRouter(prefix="/api", tags=["optimization"])


@router.get("/optimize/plan", summary="Preview full optimization plan before confirming")
async def get_optimization_plan(
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    """
    Returns the complete plan: rebalancing transfers + reserve releases,
    with rationale, amounts, channels and costs. No state is changed.
    """
    return svc.get_optimization_plan()


# ── 1. Main optimization (existing) ───────────────────────────────────────────
@router.post("/optimize", response_model=OptimizeResponse,
             summary="Apply liquidity optimization plan")
async def optimize(
    body: OptimizeRequest,
    request: Request,
    _rate: None = Depends(require_opt_rate),
):
    if not body.confirm:
        raise HTTPException(400, "Optimization requires confirm=true")
    impact_dict = svc.apply_optimization()
    from ..models.schemas import OptImpact, RiskLevel
    impact = OptImpact(
        frozen_after=impact_dict["frozen_after"],
        saved_total=impact_dict["saved_total"],
        risk_after=RiskLevel(impact_dict["risk_after"]),
        risk_after_label=impact_dict["risk_after_label"],
        alerts_resolved=impact_dict["alerts_resolved"],
    )
    return OptimizeResponse(ok=True, offline=False, impact=impact)


# ── 2. Reserve Optimization Engine ────────────────────────────────────────────
@router.get("/reserve", summary="Compute optimal reserve levels per account")
async def reserve_optimization(
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    """
    Calculates optimal_reserve, excess, and potential_release for every
    nostro account using:  optimal = avg_daily_outflow × clearing_lag × safety_factor
    """
    data = svc.get_dashboard()
    result = compute_reserve_optimization(data["accounts"], data["cashflow"])
    return result


# ── 3. Settlement Delay Forecasting ───────────────────────────────────────────
@router.get("/settlement", summary="P50/P95 settlement latency forecast per rail")
async def settlement_forecast(
    request: Request,
    day_of_week: int = Query(default=0, ge=0, le=6,
                             description="0=Monday … 6=Sunday"),
    holiday_penalty_h: float = Query(default=0.0, ge=0, le=72,
                                     description="Extra hours for holidays"),
    _rate: None = Depends(require_api_rate),
):
    return forecast_settlement_delays(
        day_of_week=day_of_week,
        holiday_penalty_hours=holiday_penalty_h,
    )


# ── 4. Intraday Liquidity Forecasting ─────────────────────────────────────────
@router.get("/intraday", summary="Hourly intraday liquidity curve and dip detection")
async def intraday_forecast(
    request: Request,
    account_id: str = Query(default="usd", description="Account to model"),
    threshold_pct: float = Query(default=0.10, ge=0.01, le=0.5,
                                  description="Dip threshold as % of opening balance"),
    _rate: None = Depends(require_api_rate),
):
    data      = svc.get_dashboard()
    cashflow  = data["cashflow"]
    accounts  = data["accounts"]
    acc       = next((a for a in accounts if a["id"] == account_id), accounts[0])

    total_bal = sum(a["balance"] for a in accounts) or 1.0
    share     = acc["balance"] / total_bal

    avg_daily_in  = sum(cashflow["inflow"])  / len(cashflow["inflow"])  * share
    avg_daily_out = sum(cashflow["outflow"]) / len(cashflow["outflow"]) * share

    result = forecast_intraday(
        daily_inflow=avg_daily_in,
        daily_outflow=avg_daily_out,
        opening_balance=acc["balance"],
        threshold_pct=threshold_pct,
    )
    result["account"] = {"id": acc["id"], "currency": acc["currency"], "bank": acc["bank"]}
    return result


# ── 5. Smart Rebalancing ──────────────────────────────────────────────────────
@router.get("/rebalance", summary="Smart rebalancing transfer recommendations")
async def rebalancing(
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    """
    Greedy deficit-filling algorithm: matches surplus accounts to deficit
    accounts by urgency, respecting transfer costs and settlement lag.
    """
    data = svc.get_dashboard()
    return compute_rebalancing(data["accounts"], data["cashflow"])


# ── 6. Scenario Simulation ────────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    volume_mult:      float        = Field(default=1.0, ge=0.1, le=10.0)
    delay_add_days:   int          = Field(default=0,   ge=0,   le=30)
    bank_unavailable: str | None   = Field(default=None, max_length=20)
    fx_shock_pct:     float        = Field(default=0.0, ge=-50.0, le=50.0)
    holiday_days:     int          = Field(default=0,   ge=0,   le=14)


@router.post("/simulate", summary="What-if scenario simulation with parametric shocks")
async def simulate(
    body: SimulateRequest,
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    """
    Apply any combination of shocks and get before/after risk comparison
    plus prioritised action instructions.
    """
    data = svc.get_dashboard()
    return simulate_scenario(
        accounts          = data["accounts"],
        cashflow          = data["cashflow"],
        volume_mult       = body.volume_mult,
        delay_add_days    = body.delay_add_days,
        bank_unavailable  = body.bank_unavailable,
        fx_shock_pct      = body.fx_shock_pct,
        holiday_days      = body.holiday_days,
    )


# ── 7. Stress scenario (legacy GET/POST) ──────────────────────────────────────
@router.post("/scenario", summary="Pre-built stress scenario")
async def run_scenario(
    body: ScenarioRequest,
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    try:
        return svc.get_scenario(body.scenario)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/scenario/{key}", summary="Pre-built stress scenario by key")
async def get_scenario(
    key: ScenarioKey,
    request: Request,
    _rate: None = Depends(require_api_rate),
):
    try:
        return svc.get_scenario(key)
    except KeyError as e:
        raise HTTPException(404, str(e))
