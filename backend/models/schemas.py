"""
schemas.py — Pydantic models for request/response validation.
All API inputs/outputs are typed and validated here.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────────


class AccountStatus(str, Enum):
    ok = "ok"
    warning = "warning"
    danger = "danger"


class AlertSeverity(str, Enum):
    ok = "ok"
    warning = "warning"
    danger = "danger"
    info = "info"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ScenarioKey(str, Enum):
    swift = "swift"
    volume = "volume"
    holiday = "holiday"
    fx = "fx"


# ── Nested models ──────────────────────────────────────────────────────────────


class LiquidityValue(BaseModel):
    value: float
    currency: str = "USD"
    unit: str = "M"


class FrozenReserves(BaseModel):
    value: float
    currency: str = "USD"
    unit: str = "M"
    prev: float


class GapRisk(BaseModel):
    level: RiskLevel
    label: str
    accounts_at_risk: int = Field(ge=0)


class Overdrafts(BaseModel):
    value: float = Field(ge=0)
    currency: str = "USD"
    change_pct: float


class Summary(BaseModel):
    total_liquidity: LiquidityValue
    frozen_reserves: FrozenReserves
    gap_risk: GapRisk
    overdrafts_30d: Overdrafts


class Account(BaseModel):
    id: str
    currency: str = Field(min_length=2, max_length=5)
    bank: str = Field(min_length=1, max_length=100)
    balance: float
    balance_unit: str = "M"
    min_reserve: float = Field(ge=0)
    fill_pct: int = Field(ge=0, le=100)
    status: AccountStatus
    incoming: str
    outgoing: str
    note: str


class AlertDetail(BaseModel):
    key: str
    value: str


class Alert(BaseModel):
    id: str
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    meta: str | None = None
    recommendation: str | None = None
    details: list[list[str]] = []


class CashFlow(BaseModel):
    days: list[str]
    inflow: list[float]
    outflow: list[float]

    @field_validator("inflow", "outflow")
    @classmethod
    def non_negative(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("Cash flow values must be non-negative")
        return v


class ForecastRow(BaseModel):
    days_ahead: int = Field(ge=1, le=90)
    obligations: str
    incoming: str
    channel: str
    ok: bool


class ClearingDelay(BaseModel):
    system: str
    delay: str
    notes: str


class OptStep(BaseModel):
    from_: str = Field(alias="from")
    to: str
    amount: str

    model_config = {"populate_by_name": True}


class OptImpact(BaseModel):
    frozen_after: float
    saved_total: float
    risk_after: RiskLevel
    risk_after_label: str
    alerts_resolved: int = Field(ge=0)


class Optimization(BaseModel):
    steps: list[OptStep]
    impact: OptImpact


class ScenarioLine(BaseModel):
    label: str
    severity: AlertSeverity
    lines: list[str]


class StressScenarios(BaseModel):
    swift: ScenarioLine
    volume: ScenarioLine
    holiday: ScenarioLine
    fx: ScenarioLine


# ── Top-level dashboard response ───────────────────────────────────────────────


class DashboardResponse(BaseModel):
    summary: Summary
    accounts: list[Account]
    alerts: list[Alert]
    cashflow: CashFlow
    forecast: list[ForecastRow]
    clearing_delays: list[ClearingDelay]
    optimization: Optimization
    stress_scenarios: StressScenarios


# ── Request models ─────────────────────────────────────────────────────────────


class OptimizeRequest(BaseModel):
    confirm: bool = True


class ScenarioRequest(BaseModel):
    scenario: ScenarioKey


class AccountFilterRequest(BaseModel):
    status: AccountStatus | None = None


class AlertFilterRequest(BaseModel):
    severity: AlertSeverity | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


# ── Response wrappers ──────────────────────────────────────────────────────────


class OptimizeResponse(BaseModel):
    ok: bool
    offline: bool = False
    impact: OptImpact


class SearchResult(BaseModel):
    type: str
    title: str
    sub: str
    target: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    offline: bool = False
