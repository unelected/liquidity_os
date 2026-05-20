"""
optimization_engine.py — Advanced optimization & analytics module.

Five sub-engines (no ML, all deterministic/statistical):

1. Reserve Optimization Engine
   Optimal reserve = max_daily_outflow × clearing_lag × safety_factor
   Excess = balance − optimal_reserve  →  potential capital release

2. Settlement Delay Forecasting
   Simulated P50/P95 latency per rail from historical distribution lookup.
   Uses day-of-week and holiday calendar adjustments.

3. Intraday Liquidity Forecasting
   Distributes daily totals across 24 hourly buckets via a
   payment-pattern weight vector (morning peak, afternoon trough, EOD surge).
   Flags hours where cumulative position dips below threshold.

4. Smart Rebalancing Recommendations
   Greedy deficit-filling: sort deficits by urgency (DCR), sort surpluses
   by availability (ERR), match greedily while respecting transfer caps.

5. Scenario Simulation (What-If)
   Parametric shocks applied to current state:
   volume_mult, delay_add_days, bank_unavailable, fx_shock_pct, holiday_days.
"""

from __future__ import annotations

from copy import deepcopy


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CLEARING_LAGS: dict[str, int] = {
    "SEPA": 1,
    "SWIFT": 3,
    "Карты": 5,
    "Внутренние": 0,
}

# Safety multiplier over clearing lag
SAFETY_FACTOR = 1.25

# Transfer cost proxy (bps per transfer, simplified)
TRANSFER_COST_BPS: dict[str, float] = {
    "SWIFT": 15.0,
    "SEPA": 3.0,
    "Карты": 0.0,
    "Внутренние": 0.0,
}

# Historical P50/P95 latency in hours per rail (simulated from known ranges)
LATENCY_TABLE: dict[str, dict[str, float]] = {
    "SEPA": {"p50": 4.0, "p95": 20.0},
    "SWIFT": {"p50": 28.0, "p95": 60.0},
    "Карты": {"p50": 72.0, "p95": 110.0},
    "Внутренние": {"p50": 0.1, "p95": 0.5},
}

# Day-of-week multiplier for latency (Mon=0 … Sun=6)
DOW_LATENCY_MULT = [1.0, 1.0, 1.0, 1.0, 1.3, 1.8, 1.9]

# Intraday payment weight vector — 24 hours (index = hour UTC)
# Peak: 09-11, 14-15; trough: 00-07; EOD surge: 16-17
_INTRADAY_WEIGHTS = [
    0.5,
    0.4,
    0.3,
    0.3,
    0.4,
    0.6,  # 00-05
    1.0,
    1.5,
    2.5,
    3.5,
    3.8,
    3.2,  # 06-11
    2.8,
    2.4,
    3.0,
    3.2,
    3.6,
    2.8,  # 12-17
    2.0,
    1.5,
    1.2,
    1.0,
    0.8,
    0.6,  # 18-23
]
_INTRADAY_TOTAL = sum(_INTRADAY_WEIGHTS)
_INTRADAY_NORM = [w / _INTRADAY_TOTAL for w in _INTRADAY_WEIGHTS]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RESERVE OPTIMIZATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


def compute_reserve_optimization(accounts: list[dict], cashflow: dict) -> dict:
    """
    For each account:
      optimal_reserve = avg_daily_outflow × max_clearing_lag × SAFETY_FACTOR
      excess          = max(0, balance − optimal_reserve)
      potential_release = excess × 0.80  (keep 20% as discretionary buffer)

    Returns per-account breakdown and portfolio totals.
    """
    outflows = cashflow.get("outflow", [])
    avg_daily = sum(outflows) / len(outflows) if outflows else 0.0

    # Worst-case clearing lag in the portfolio
    max_lag = max(CLEARING_LAGS.values())

    per_account: list[dict] = []
    total_current = 0.0
    total_optimal = 0.0
    total_excess = 0.0
    total_release = 0.0
    instructions: list[dict] = []

    for acc in accounts:
        bal = acc["balance"]
        min_res = acc["min_reserve"]
        # Scale avg daily by the account's share of portfolio (simplified)
        total_bal = sum(a["balance"] for a in accounts) or 1.0
        share = bal / total_bal
        acct_daily_out = avg_daily * share

        optimal = max(min_res, round(acct_daily_out * max_lag * SAFETY_FACTOR, 2))
        excess = max(0.0, round(bal - optimal, 2))
        release = round(excess * 0.80, 2)

        total_current += bal
        total_optimal += optimal
        total_excess += excess
        total_release += release

        row = {
            "id": acc["id"],
            "currency": acc["currency"],
            "bank": acc["bank"],
            "current_reserve": bal,
            "optimal_reserve": optimal,
            "excess": excess,
            "potential_release": release,
            "status": acc["status"],
        }
        per_account.append(row)

        # Generate instructions for accounts with meaningful excess
        if release >= 0.1:
            instructions.append(
                {
                    "priority": 1 if acc["status"] == "ok" and excess > 1.0 else 2,
                    "account_id": acc["id"],
                    "action": "release_excess",
                    "label": f"Высвободить {release}M {acc['currency']} из {acc['bank']}",
                    "amount": release,
                    "currency": acc["currency"],
                    "rationale": (
                        f"Остаток {bal}M превышает оптимальный резерв {optimal}M "
                        f"на {excess}M. 80% избытка ({release}M) можно безопасно перераспределить."
                    ),
                    "method": f"Оптимальный резерв = avg_daily_outflow × {max_lag}д × {SAFETY_FACTOR}",
                }
            )

    instructions.sort(key=lambda x: x["priority"])

    return {
        "per_account": per_account,
        "portfolio": {
            "total_current_reserves": round(total_current, 2),
            "total_optimal_reserves": round(total_optimal, 2),
            "total_excess": round(total_excess, 2),
            "total_potential_release": round(total_release, 2),
            "efficiency_pct": round(
                (total_optimal / total_current * 100) if total_current else 0, 1
            ),
        },
        "instructions": instructions,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SETTLEMENT DELAY FORECASTING
# ═══════════════════════════════════════════════════════════════════════════════


def forecast_settlement_delays(
    day_of_week: int = 0,
    holiday_penalty_hours: float = 0.0,
) -> dict:
    """
    Returns expected P50/P95 settlement time for each rail,
    adjusted for day-of-week and holidays.

    day_of_week: 0=Mon … 6=Sun
    holiday_penalty_hours: additional hours added to all rails (e.g. 8 for next-day)
    """
    mult = DOW_LATENCY_MULT[day_of_week % 7]
    rails: list[dict] = []
    recommendations: list[str] = []

    for rail, base in LATENCY_TABLE.items():
        p50 = round(base["p50"] * mult + holiday_penalty_hours, 1)
        p95 = round(base["p95"] * mult + holiday_penalty_hours, 1)
        lag_days = CLEARING_LAGS.get(rail, 0)

        risk = "low"
        if p95 > 48:
            risk = "high"
        elif p95 > 24:
            risk = "medium"

        rails.append(
            {
                "rail": rail,
                "p50_hours": p50,
                "p95_hours": p95,
                "lag_days": lag_days,
                "dow_multiplier": mult,
                "risk": risk,
            }
        )

        if risk == "high":
            recommendations.append(
                f"{rail}: ожидаемая задержка P95={p95}ч — "
                f"направьте платежи через более быстрый канал или создайте буфер заранее."
            )

    # Sort slowest first
    rails.sort(key=lambda r: r["p95_hours"], reverse=True)

    return {
        "day_of_week": day_of_week,
        "holiday_penalty_h": holiday_penalty_hours,
        "rails": rails,
        "recommendations": recommendations,
        "fastest_rail": rails[-1]["rail"],
        "slowest_rail": rails[0]["rail"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. INTRADAY LIQUIDITY FORECASTING
# ═══════════════════════════════════════════════════════════════════════════════


def forecast_intraday(
    daily_inflow: float,
    daily_outflow: float,
    opening_balance: float,
    threshold_pct: float = 0.10,
) -> dict:
    """
    Distributes daily_inflow and daily_outflow across 24 hours
    using the payment-pattern weight vector.

    threshold_pct: minimum balance as % of opening_balance below which = dip alert.

    Returns hourly curve and list of dip windows.
    """
    threshold = opening_balance * threshold_pct
    hours: list[dict] = []
    balance = opening_balance
    dips: list[dict] = []

    for h, w in enumerate(_INTRADAY_NORM):
        # Outflows slightly front-loaded, inflows slightly back-loaded
        out_shift = 0.6 if h < 12 else 0.4
        in_shift = 0.4 if h < 12 else 0.6
        net = round(daily_inflow * w * in_shift - daily_outflow * w * out_shift, 3)
        balance = round(balance + net, 3)

        entry = {
            "hour": h,
            "label": f"{h:02d}:00",
            "inflow": round(daily_inflow * w * in_shift, 3),
            "outflow": round(daily_outflow * w * out_shift, 3),
            "net": net,
            "balance": balance,
            "dip": balance < threshold,
        }
        hours.append(entry)

        if balance < threshold:
            dips.append(
                {
                    "hour": h,
                    "label": f"{h:02d}:00",
                    "balance": balance,
                    "deficit": round(threshold - balance, 3),
                }
            )

    return {
        "opening_balance": opening_balance,
        "closing_balance": balance,
        "threshold": round(threshold, 3),
        "daily_net": round(daily_inflow - daily_outflow, 3),
        "hours": hours,
        "dips": dips,
        "dip_count": len(dips),
        "worst_dip": min(hours, key=lambda h: h["balance"]) if hours else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SMART REBALANCING RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════════


def compute_rebalancing(accounts: list[dict], cashflow: dict) -> dict:
    """
    Greedy matching algorithm:
    1. Classify each account as deficit or surplus using DCR and ERR.
    2. Sort deficits by urgency (lowest DCR first).
    3. Sort surpluses by availability (highest excess first).
    4. Greedily match: transfer min(deficit_need, surplus_available).
    5. Annotate each transfer with estimated cost and settlement channel.

    Returns prioritised list of transfer instructions.
    """
    outflows = cashflow.get("outflow", [])
    avg_daily = sum(outflows) / len(outflows) if outflows else 1.0

    deficits: list[dict] = []
    surpluses: list[dict] = []

    for acc in accounts:
        bal = acc["balance"]
        min_res = acc["min_reserve"]
        avg_d = avg_daily * (bal / (sum(a["balance"] for a in accounts) or 1))
        dcr = bal / avg_d if avg_d else 99.0
        excess = max(0.0, bal - min_res)
        err = excess / bal if bal else 0.0

        if acc["status"] in ("danger", "warning") or dcr < 3.0:
            need = round(min_res * 1.5 - bal, 2)
            if need > 0:
                deficits.append(
                    {
                        "account_id": acc["id"],
                        "currency": acc["currency"],
                        "bank": acc["bank"],
                        "need": need,
                        "dcr": round(dcr, 2),
                        "urgency": "critical" if acc["status"] == "danger" else "high",
                    }
                )

        if err > 0.40 and excess > 0.2:
            surpluses.append(
                {
                    "account_id": acc["id"],
                    "currency": acc["currency"],
                    "bank": acc["bank"],
                    "available": round(excess * 0.80, 2),
                    "err": round(err, 2),
                }
            )

    deficits.sort(key=lambda d: (0 if d["urgency"] == "critical" else 1, d["dcr"]))
    surpluses.sort(key=lambda s: s["available"], reverse=True)

    transfers: list[dict] = []
    surplus_pool = deepcopy(surpluses)

    for deficit in deficits:
        remaining = deficit["need"]
        for surplus in surplus_pool:
            if surplus["available"] <= 0 or remaining <= 0:
                continue
            amount = round(min(remaining, surplus["available"]), 2)

            # Determine best channel
            if deficit["currency"] == surplus["currency"]:
                channel = "SEPA" if deficit["currency"] == "EUR" else "Внутренние"
            else:
                channel = "SWIFT"

            lag = CLEARING_LAGS.get(channel, 1)
            cost = round(amount * TRANSFER_COST_BPS[channel] / 10000, 4)

            transfers.append(
                {
                    "priority": len(transfers) + 1,
                    "from_account": surplus["account_id"],
                    "from_bank": surplus["bank"],
                    "from_currency": surplus["currency"],
                    "to_account": deficit["account_id"],
                    "to_bank": deficit["bank"],
                    "to_currency": deficit["currency"],
                    "amount": amount,
                    "channel": channel,
                    "settlement_lag_days": lag,
                    "estimated_cost_usd": cost,
                    "urgency": deficit["urgency"],
                    "label": (
                        f"{surplus['currency']}/{surplus['bank']} → "
                        f"{deficit['currency']}/{deficit['bank']}"
                    ),
                    "rationale": (
                        f"Перевод {amount}M покроет дефицит {deficit['bank']} "
                        f"(DCR={deficit['dcr']}д). Канал: {channel}, лаг: {lag}д, "
                        f"стоимость перевода: ${cost * 1000:.0f} (оценка)."
                    ),
                    "liquidity_improvement": amount,
                }
            )

            surplus["available"] = round(surplus["available"] - amount, 2)
            remaining = round(remaining - amount, 2)

    total_moved = round(sum(t["amount"] for t in transfers), 2)
    total_cost = round(sum(t["estimated_cost_usd"] for t in transfers), 4)
    covered_deficits = len({t["to_account"] for t in transfers})

    return {
        "transfers": transfers,
        "deficits_found": len(deficits),
        "surpluses_found": len(surpluses),
        "deficits_covered": covered_deficits,
        "total_moved": total_moved,
        "total_cost_usd": total_cost,
        "summary": (
            f"{len(transfers)} перевод(а) · {total_moved}M перераспределено · "
            f"покрыто {covered_deficits}/{len(deficits)} дефицит(а)"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SCENARIO SIMULATION (WHAT-IF)
# ═══════════════════════════════════════════════════════════════════════════════


def simulate_scenario(
    accounts: list[dict],
    cashflow: dict,
    *,
    volume_mult: float = 1.0,  # e.g. 2.0 = double volume
    delay_add_days: int = 0,  # extra clearing days on all rails
    bank_unavailable: str | None = None,  # account_id to remove
    fx_shock_pct: float = 0.0,  # % change on EUR balances (negative = drop)
    holiday_days: int = 0,  # number of additional holiday days
) -> dict:
    """
    Applies parametric shocks to current state and re-runs risk scoring.
    Returns before/after comparison with impact assessment.
    """
    shocked_accounts = deepcopy(accounts)
    shocked_cashflow = deepcopy(cashflow)
    applied_shocks: list[str] = []
    instructions: list[dict] = []

    # — Volume shock
    if volume_mult != 1.0:
        shocked_cashflow["outflow"] = [
            round(v * volume_mult, 2) for v in shocked_cashflow["outflow"]
        ]
        shocked_cashflow["inflow"] = [
            round(v * volume_mult * 0.90, 2) for v in shocked_cashflow["inflow"]
        ]
        applied_shocks.append(
            f"Объём ×{volume_mult} (outflow ×{volume_mult}, inflow ×{volume_mult * 0.9:.1f})"
        )
        if volume_mult > 1.5:
            instructions.append(
                {
                    "priority": 1,
                    "action": "increase_reserves",
                    "label": f"Увеличить резервы на {round((volume_mult - 1) * 100)}% на всех счетах",
                    "rationale": f"Объём платежей вырос в {volume_mult}x — текущие резервы покроют лишь {round(1 / volume_mult * 100)}% потребности.",
                }
            )

    # — Delay shock
    eff_lags = {k: v + delay_add_days for k, v in CLEARING_LAGS.items()}
    if delay_add_days > 0:
        applied_shocks.append(f"Задержки клиринга +{delay_add_days}д по всем каналам")
        instructions.append(
            {
                "priority": 1,
                "action": "prefund",
                "label": f"Пре-фондировать критические счета на {delay_add_days * 2} дня вперёд",
                "rationale": f"Задержка {delay_add_days}д блокирует входящие; нужен буфер до нормализации.",
            }
        )

    # — Bank unavailability
    if bank_unavailable:
        before_count = len(shocked_accounts)
        shocked_accounts = [a for a in shocked_accounts if a["id"] != bank_unavailable]
        removed = before_count - len(shocked_accounts)
        if removed:
            removed_acc = next((a for a in accounts if a["id"] == bank_unavailable), {})
            applied_shocks.append(
                f"Счёт {removed_acc.get('currency', '?')}/{removed_acc.get('bank', '?')} недоступен"
            )
            instructions.append(
                {
                    "priority": 1,
                    "action": "reroute",
                    "label": f"Перенаправить платежи с {removed_acc.get('bank', '?')} на резервные банки",
                    "rationale": "Недоступность банка требует немедленного переключения на альтернативные каналы.",
                }
            )

    # — FX shock on EUR accounts
    if fx_shock_pct != 0.0:
        for acc in shocked_accounts:
            if acc["currency"] == "EUR":
                acc["balance"] = round(acc["balance"] * (1 + fx_shock_pct / 100), 2)
                acc["fill_pct"] = max(
                    0, min(100, int(acc["fill_pct"] * (1 + fx_shock_pct / 200)))
                )
        applied_shocks.append(
            f"EUR/USD {'+' if fx_shock_pct > 0 else ''}{fx_shock_pct}%"
        )
        if fx_shock_pct < -3:
            instructions.append(
                {
                    "priority": 2,
                    "action": "hedge",
                    "label": f"Открыть EUR/USD форвард на сумму EUR-позиций",
                    "rationale": f"Курсовой риск {abs(fx_shock_pct)}% снижает EUR-ликвидность в USD-эквиваленте.",
                }
            )

    # — Holiday days
    if holiday_days > 0:
        sepa_blocked = (
            sum(shocked_cashflow["inflow"][:holiday_days])
            if holiday_days <= len(shocked_cashflow["inflow"])
            else 0
        )
        applied_shocks.append(f"Банковские праздники: {holiday_days}д заморожено")
        instructions.append(
            {
                "priority": 2,
                "action": "prefund_holiday",
                "label": f"Создать буфер €{round(sepa_blocked, 1)}M для покрытия {holiday_days} праздничных дней",
                "rationale": f"SEPA/SWIFT не проводят платежи в праздники; ожидаемый заблокированный объём ~{round(sepa_blocked, 1)}M.",
            }
        )

    # Re-score risk after shocks
    from .liquidity_service import (
        _compute_gap_risk,
        _compute_frozen,
        detect_cashflow_anomalies,
    )

    before_risk = _compute_gap_risk(accounts)
    after_risk = _compute_gap_risk(shocked_accounts)
    before_frozen = _compute_frozen(accounts)
    after_frozen = _compute_frozen(shocked_accounts)
    after_anomalies = detect_cashflow_anomalies(shocked_cashflow)

    # Liquidity sufficiency check
    total_after = sum(a["balance"] for a in shocked_accounts)
    avg_out_after = sum(shocked_cashflow["outflow"]) / max(
        len(shocked_cashflow["outflow"]), 1
    )
    max_lag = max(eff_lags.values())
    required = avg_out_after * max_lag * SAFETY_FACTOR
    reserve_sufficiency_pct = (
        round(total_after / required * 100, 1) if required else 999.0
    )

    instructions.sort(key=lambda i: i["priority"])

    return {
        "applied_shocks": applied_shocks,
        "before": {
            "risk_level": before_risk["level"],
            "risk_label": before_risk["label"],
            "frozen": before_frozen,
            "total_balance": round(sum(a["balance"] for a in accounts), 2),
        },
        "after": {
            "risk_level": after_risk["level"],
            "risk_label": after_risk["label"],
            "frozen": after_frozen,
            "total_balance": round(total_after, 2),
            "accounts_left": len(shocked_accounts),
        },
        "impact": {
            "risk_changed": before_risk["level"] != after_risk["level"],
            "balance_delta": round(
                total_after - sum(a["balance"] for a in accounts), 2
            ),
            "anomalies_after": len(after_anomalies),
            "reserve_sufficiency_pct": reserve_sufficiency_pct,
            "sufficient": reserve_sufficiency_pct >= 100,
        },
        "instructions": instructions,
    }
