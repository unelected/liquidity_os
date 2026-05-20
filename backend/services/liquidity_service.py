"""
liquidity_service.py — Business logic layer.

Analytics methods used (no ML, pure economics/statistics):

1. Weighted Risk Score
   score = Σ (1 - fill_pct/100) × severity_weight
   Aggregates per-account scores into low/medium/high portfolio risk.

2. Z-score anomaly detection (cash flow)
   z = |x - μ| / σ  — flags days that deviate > 1.8σ from the 7-day mean.
   Standard in fraud detection and treasury monitoring.

3. Days Coverage Ratio (DCR)  — клиринговые разрывы
   DCR = balance / avg_daily_obligations
   DCR < clearing_lag_days  →  gap risk alert.
   Measures how many days the current balance covers upcoming payments.

4. Gini coefficient of balance distribution — неэффективное распределение
   Gini ∈ [0,1].  0 = perfectly even, 1 = all capital in one account.
   Gini > 0.55 in a multi-account portfolio signals structural imbalance.

5. Excess Reserve Ratio (ERR) — избыточные резервы
   ERR = (balance - min_reserve) / balance
   Per-account ERR > 0.70 flags capital locked up above the safety buffer.
   Portfolio-level: sum(excess) / sum(balances).
"""

from __future__ import annotations

import copy
import math

from ..core.seed_data import SEED
from ..models.schemas import ScenarioKey


# ── In-memory state ────────────────────────────────────────────────────────────
_state: dict = copy.deepcopy(SEED)


def reset_state() -> None:
    global _state
    _state = copy.deepcopy(SEED)


# ── Dashboard ──────────────────────────────────────────────────────────────────


def get_dashboard() -> dict:
    data = copy.deepcopy(_state)
    data["summary"]["gap_risk"] = _compute_gap_risk(data["accounts"])
    data["summary"]["frozen_reserves"]["value"] = _compute_frozen(data["accounts"])
    # Merge in dynamically computed alerts
    data["alerts"] = _merge_dynamic_alerts(data["alerts"], data)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# 1. WEIGHTED RISK SCORE
# ═══════════════════════════════════════════════════════════════════════════════


def _compute_gap_risk(accounts: list[dict]) -> dict:
    weights = {"danger": 3.0, "warning": 1.5, "ok": 0.0}
    danger_count = 0
    total_score = 0.0

    for acc in accounts:
        w = weights.get(acc["status"], 0.0)
        total_score += (1.0 - acc["fill_pct"] / 100.0) * w
        if acc["status"] == "danger":
            danger_count += 1

    if danger_count == 0 and total_score <= 1.5:
        level, label = "low", "Низкий"
    elif danger_count > 1 or total_score > 3.0:
        level, label = "high", "Высокий"
    else:
        level, label = "medium", "Средний"

    return {"level": level, "label": label, "accounts_at_risk": danger_count}


def _compute_frozen(accounts: list[dict]) -> float:
    total = 0.0
    for acc in accounts:
        if acc["status"] == "ok" and acc["fill_pct"] > 75:
            total += acc["balance"] * ((acc["fill_pct"] - 75) / 100.0)
    return round(total, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Z-SCORE ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

ANOMALY_THRESHOLD = 1.8  # σ — standard in treasury monitoring


def detect_cashflow_anomalies(cashflow: dict) -> list[dict]:
    """
    For each series (inflow/outflow) compute z = |x - μ| / σ.
    Returns days where z > ANOMALY_THRESHOLD.
    """
    anomalies = []
    for series_key in ("inflow", "outflow"):
        series = cashflow[series_key]
        n = len(series)
        if n < 3:
            continue
        mean = sum(series) / n
        std = math.sqrt(sum((x - mean) ** 2 for x in series) / n)
        if std == 0:
            continue
        for i, val in enumerate(series):
            z = abs(val - mean) / std
            if z > ANOMALY_THRESHOLD:
                anomalies.append(
                    {
                        "day": cashflow["days"][i],
                        "series": series_key,
                        "value": val,
                        "z_score": round(z, 2),
                        "mean": round(mean, 2),
                        "deviation_pct": round((val - mean) / mean * 100, 1),
                    }
                )
    return anomalies


def _build_anomaly_alerts(cashflow: dict) -> list[dict]:
    """Converts cashflow anomalies into alert objects."""
    anomalies = detect_cashflow_anomalies(cashflow)
    if not anomalies:
        return []

    worst = max(anomalies, key=lambda a: a["z_score"])
    direction = "входящих" if worst["series"] == "inflow" else "исходящих"
    sign = "↑" if worst["value"] > worst["mean"] else "↓"
    severity = "danger" if worst["z_score"] > 2.5 else "warning"

    return [
        {
            "id": "alert-anomaly-txn",
            "severity": severity,
            "title": f"Аномалия транзакций — {worst['day']} ({direction})",
            "description": (
                f"Объём {direction} {sign} {abs(worst['deviation_pct'])}% от нормы "
                f"({worst['value']}M vs среднее {worst['mean']}M). "
                f"Z-score: {worst['z_score']} σ. "
                f"Всего аномальных наблюдений: {len(anomalies)}."
            ),
            "meta": f"Z-score метод · порог {ANOMALY_THRESHOLD}σ · {len(anomalies)} аномали(й)",
            "recommendation": "Проверьте источник всплеска. Возможны ошибочные проводки или нестандартные платежи.",
            "details": [
                ["Метод", f"Z-score (σ = {ANOMALY_THRESHOLD})"],
                ["День", worst["day"]],
                ["Серия", direction],
                ["Значение", f"{worst['value']}M"],
                ["Среднее (7д)", f"{worst['mean']}M"],
                ["Отклонение", f"{worst['deviation_pct']}%"],
                ["Z-score", str(worst["z_score"])],
                ["Аномалий всего", str(len(anomalies))],
                [
                    "Серьёзность",
                    "Критическая" if severity == "danger" else "Повышенная",
                ],
            ],
        }
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DAYS COVERAGE RATIO — кассовые разрывы из-за задержек клиринга
# ═══════════════════════════════════════════════════════════════════════════════

# Clearing lag by channel in business days
CLEARING_LAGS: dict[str, int] = {
    "SEPA": 1,
    "SWIFT": 3,
    "Карты": 5,
    "Внутренние": 0,
}
DCR_DANGER_THRESHOLD = 1.0  # balance covers < 1 day → critical
DCR_WARNING_THRESHOLD = 2.0  # balance covers < 2 days → warning


def _build_clearing_gap_alerts(
    accounts: list[dict], forecast: list[dict]
) -> list[dict]:
    """
    Days Coverage Ratio per account:
        DCR = balance / avg_daily_obligations

    If DCR < clearing_lag for the dominant channel → gap risk.
    Uses forecast rows to estimate avg daily obligations.
    """
    if not forecast:
        return []

    # Sum obligations that look like a given currency (simplified: use all)
    # We use the forecast's channel to look up the lag
    worst_channel = max(CLEARING_LAGS, key=lambda c: CLEARING_LAGS[c])
    worst_lag = CLEARING_LAGS[worst_channel]

    alerts = []
    for acc in accounts:
        # Skip accounts with no meaningful balance
        if acc["balance"] <= 0:
            continue

        # Rough avg daily obligation: min_reserve × 0.5 as a proxy
        # (In production this would come from scheduled payment data)
        avg_daily_obl = acc["min_reserve"] * 0.5
        if avg_daily_obl == 0:
            continue

        dcr = acc["balance"] / avg_daily_obl

        # Check against the highest-lag channel (worst case)
        if dcr < DCR_DANGER_THRESHOLD:
            severity = "danger"
            verdict = (
                f"Критический риск разрыва (DCR={dcr:.1f} < {DCR_DANGER_THRESHOLD})"
            )
        elif dcr < worst_lag:
            severity = "warning"
            verdict = f"Возможен разрыв при задержке клиринга (DCR={dcr:.1f} дн.)"
        else:
            continue  # account is fine

        alerts.append(
            {
                "id": f"alert-clearing-{acc['id']}",
                "severity": severity,
                "title": f"Риск кассового разрыва (клиринг) — {acc['currency']} / {acc['bank']}",
                "description": (
                    f"Days Coverage Ratio: {dcr:.1f} дн. "
                    f"При задержке {worst_channel} ({worst_lag} дн.) "
                    f"остаток {acc['balance']}M {acc['currency']} может не покрыть обязательства."
                ),
                "meta": f"DCR = {dcr:.2f} · метод: остаток ÷ среднедневные обязательства",
                "recommendation": (
                    f"Пополните счёт минимум до {acc['min_reserve'] * worst_lag:.1f}M "
                    f"для покрытия {worst_lag}-дневного клирингового лага."
                ),
                "details": [
                    ["Метод", "Days Coverage Ratio (DCR)"],
                    ["Счёт", f"{acc['currency']} / {acc['bank']}"],
                    ["Текущий остаток", f"{acc['balance']}M {acc['currency']}"],
                    ["Мин. резерв", f"{acc['min_reserve']}M"],
                    ["Среднедн. обязат.", f"~{avg_daily_obl:.2f}M"],
                    ["DCR", f"{dcr:.2f} дн."],
                    ["Лаг клиринга (макс)", f"{worst_lag} дн. ({worst_channel})"],
                    ["Статус", verdict],
                ],
            }
        )

    return alerts


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GINI COEFFICIENT — неэффективное распределение средств
# ═══════════════════════════════════════════════════════════════════════════════

GINI_WARNING_THRESHOLD = 0.45
GINI_DANGER_THRESHOLD = 0.60


def _gini(values: list[float]) -> float:
    """
    Gini coefficient for a list of non-negative values.
    Formula: G = (2 * Σ i*x_i) / (n * Σ x_i) - (n+1)/n
    where x_i are sorted in ascending order and i is 1-indexed.
    Returns value in [0, 1].
    """
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    xs = sorted(values)
    total = sum(xs)
    weighted_sum = sum((i + 1) * x for i, x in enumerate(xs))
    return round((2 * weighted_sum) / (n * total) - (n + 1) / n, 4)


def _build_distribution_alert(accounts: list[dict]) -> list[dict]:
    """
    Computes Gini on account balances.
    High Gini → some accounts have way more capital than others → structural waste.
    """
    balances = [acc["balance"] for acc in accounts if acc["balance"] > 0]
    if len(balances) < 2:
        return []

    g = _gini(balances)

    if g < GINI_WARNING_THRESHOLD:
        return []

    severity = "danger" if g >= GINI_DANGER_THRESHOLD else "warning"

    # Find the most and least loaded accounts
    max_acc = max(accounts, key=lambda a: a["balance"])
    min_acc = min(accounts, key=lambda a: a["balance"])
    imbalance_ratio = max_acc["balance"] / max(min_acc["balance"], 0.01)

    return [
        {
            "id": "alert-distribution",
            "severity": severity,
            "title": "Неэффективное распределение средств между счетами",
            "description": (
                f"Коэффициент Джини балансов: {g:.2f} "
                f"(норма < {GINI_WARNING_THRESHOLD}). "
                f"Разброс: {max_acc['currency']}/{max_acc['bank']} в {imbalance_ratio:.1f}x "
                f"превышает {min_acc['currency']}/{min_acc['bank']}. "
                f"Часть капитала заморожена в профицитных счетах."
            ),
            "meta": f"Gini = {g:.3f} · метод: коэффициент концентрации балансов",
            "recommendation": (
                f"Перераспределите часть остатка с {max_acc['currency']}/{max_acc['bank']} "
                f"на дефицитные счета. Целевой Gini < {GINI_WARNING_THRESHOLD}."
            ),
            "details": [
                ["Метод", "Коэффициент Джини (Gini)"],
                ["Gini (факт)", str(g)],
                ["Gini (норма)", f"< {GINI_WARNING_THRESHOLD}"],
                [
                    "Макс. остаток",
                    f"{max_acc['balance']}M ({max_acc['currency']}/{max_acc['bank']})",
                ],
                [
                    "Мин. остаток",
                    f"{min_acc['balance']}M ({min_acc['currency']}/{min_acc['bank']})",
                ],
                ["Дисбаланс (ratio)", f"{imbalance_ratio:.1f}x"],
                ["Счетов в анализе", str(len(balances))],
                [
                    "Серьёзность",
                    "Критическая" if severity == "danger" else "Повышенная",
                ],
            ],
        }
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. EXCESS RESERVE RATIO — избыточные резервы
# ═══════════════════════════════════════════════════════════════════════════════

ERR_WARNING_THRESHOLD = 0.55  # >55% above min_reserve → warning
ERR_DANGER_THRESHOLD = 0.75  # >75% above min_reserve → danger


def _build_excess_reserve_alerts(accounts: list[dict]) -> list[dict]:
    """
    Excess Reserve Ratio per account:
        ERR = (balance - min_reserve) / balance

    ERR > threshold → capital is locked above the safety buffer.
    Also computes portfolio-level excess as % of total capital.
    """
    alerts = []
    total_balance = sum(a["balance"] for a in accounts)
    total_excess = 0.0

    per_account: list[dict] = []
    for acc in accounts:
        if acc["balance"] <= 0 or acc["min_reserve"] <= 0:
            continue
        excess = acc["balance"] - acc["min_reserve"]
        if excess <= 0:
            continue
        err = excess / acc["balance"]
        total_excess += excess
        if err >= ERR_WARNING_THRESHOLD:
            per_account.append({**acc, "err": err, "excess": round(excess, 2)})

    portfolio_err = total_excess / total_balance if total_balance > 0 else 0.0

    if not per_account and portfolio_err < ERR_WARNING_THRESHOLD:
        return []

    # Pick the worst offender for the alert title
    if per_account:
        worst = max(per_account, key=lambda a: a["err"])
        severity = "danger" if worst["err"] >= ERR_DANGER_THRESHOLD else "warning"
        frozen_str = f"~{round(total_excess, 1)}M"

        alerts.append(
            {
                "id": "alert-excess-reserves",
                "severity": severity,
                "title": "Избыточные резервы — капитал заморожен",
                "description": (
                    f"Общий избыток выше минимального резерва: {frozen_str}. "
                    f"Наибольший: {worst['currency']}/{worst['bank']} — "
                    f"ERR {worst['err'] * 100:.0f}% (остаток {worst['balance']}M, "
                    f"мин. резерв {worst['min_reserve']}M). "
                    f"Портфельный ERR: {portfolio_err * 100:.0f}%."
                ),
                "meta": f"ERR = {worst['err'] * 100:.0f}% · метод: (остаток − резерв) ÷ остаток",
                "recommendation": (
                    f"Высвободите ~{frozen_str} из профицитных счетов. "
                    f"Направьте на погашение дефицита EUR/Barclays или в доходные инструменты."
                ),
                "details": [
                    ["Метод", "Excess Reserve Ratio (ERR)"],
                    ["Наибольший ERR", f"{worst['currency']}/{worst['bank']}"],
                    ["ERR (факт)", f"{worst['err'] * 100:.1f}%"],
                    ["ERR (порог)", f"{ERR_WARNING_THRESHOLD * 100:.0f}%"],
                    ["Остаток счёта", f"{worst['balance']}M"],
                    ["Мин. резерв", f"{worst['min_reserve']}M"],
                    ["Избыток (счёт)", f"{worst['excess']}M"],
                    ["Избыток (портфель)", frozen_str],
                    ["Портфельный ERR", f"{portfolio_err * 100:.1f}%"],
                ],
            }
        )

    return alerts


# ═══════════════════════════════════════════════════════════════════════════════
# MERGE — combine static + dynamic alerts
# ═══════════════════════════════════════════════════════════════════════════════

# IDs of alerts that are dynamically computed — never duplicated from seed
_DYNAMIC_IDS = {
    "alert-anomaly-txn",
    "alert-distribution",
    "alert-excess-reserves",
    "alert-reserve-suboptimal",
    "alert-settlement-delay",
    "alert-intraday-dip",
    "alert-rebalance-needed",
}
_CLEARING_PREFIX = "alert-clearing-"


# ── Additional lightweight alerts (new modules) ────────────────────────────────


def _build_reserve_level_alert(accounts: list[dict], cashflow: dict) -> list[dict]:
    """Flags when current reserves are significantly above the computed optimal."""
    from .optimization_engine import compute_reserve_optimization

    result = compute_reserve_optimization(accounts, cashflow)
    portfolio = result["portfolio"]
    excess = portfolio["total_excess"]
    eff = portfolio["efficiency_pct"]
    if eff >= 85.0:
        return []
    severity = "danger" if eff < 60.0 else "warning"
    release = portfolio["total_potential_release"]
    return [
        {
            "id": "alert-reserve-suboptimal",
            "severity": severity,
            "title": "Резервы выше оптимального уровня",
            "description": (
                f"Эффективность резервов: {eff}% от оптимума. "
                f"Избыток по портфелю: {excess}M. "
                f"Потенциал высвобождения: ~{release}M без увеличения риска."
            ),
            "meta": f"Reserve Engine · оптимальный резерв = avg_outflow × lag × {1.25}",
            "recommendation": (
                f"Перейдите в раздел оптимизации для детального плана высвобождения {release}M."
            ),
            "details": [
                ["Метод", "Reserve Optimization Engine"],
                ["Эффективность", f"{eff}%"],
                ["Текущие резервы", f"{portfolio['total_current_reserves']}M"],
                ["Оптимальные резервы", f"{portfolio['total_optimal_reserves']}M"],
                ["Избыток", f"{excess}M"],
                ["Потенциал высвобожд.", f"~{release}M"],
            ],
        }
    ]


def _build_settlement_delay_alert(cashflow: dict) -> list[dict]:
    """Alerts when weekend/holiday penalties push P95 latency above 48h."""
    import datetime

    dow = datetime.datetime.utcnow().weekday()
    from .optimization_engine import forecast_settlement_delays

    result = forecast_settlement_delays(day_of_week=dow, holiday_penalty_hours=0)
    high_risk_rails = [r for r in result["rails"] if r["risk"] == "high"]
    if not high_risk_rails:
        return []
    worst = high_risk_rails[0]
    return [
        {
            "id": "alert-settlement-delay",
            "severity": "warning",
            "title": f"Повышенная задержка расчётов — {worst['rail']} ({worst['p95_hours']}ч P95)",
            "description": (
                f"Сегодня {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][dow]}. "
                f"{worst['rail']}: P50={worst['p50_hours']}ч, P95={worst['p95_hours']}ч. "
                f"Используйте более быстрый канал или создайте буфер заранее."
            ),
            "meta": f"Settlement Forecast · P95 > 48ч · множитель дня: {worst['dow_multiplier']}x",
            "recommendation": (
                f"Направьте срочные платежи через {result['fastest_rail']} — "
                f"самый быстрый доступный канал."
            ),
            "details": [
                ["Метод", "Settlement Delay Forecasting (P50/P95)"],
                ["Канал", worst["rail"]],
                ["P50", f"{worst['p50_hours']}ч"],
                ["P95", f"{worst['p95_hours']}ч"],
                ["День недели", ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][dow]],
                ["Лаг клиринга", f"{worst['lag_days']}д"],
                ["Быстрый канал", result["fastest_rail"]],
            ],
        }
    ]


def _build_intraday_dip_alert(accounts: list[dict], cashflow: dict) -> list[dict]:
    """Alerts when intraday model predicts a balance dip below 10% threshold."""
    from .optimization_engine import forecast_intraday

    # Use the most at-risk account (lowest fill_pct)
    risky = min(accounts, key=lambda a: a["fill_pct"])
    total_bal = sum(a["balance"] for a in accounts) or 1.0
    share = risky["balance"] / total_bal
    avg_in = sum(cashflow["inflow"]) / len(cashflow["inflow"]) * share
    avg_out = sum(cashflow["outflow"]) / len(cashflow["outflow"]) * share
    result = forecast_intraday(avg_in, avg_out, risky["balance"])
    if result["dip_count"] == 0:
        return []
    worst = result["worst_dip"]
    return [
        {
            "id": "alert-intraday-dip",
            "severity": "warning",
            "title": f"Внутридневной дефицит — {risky['currency']}/{risky['bank']} в {worst['label']}",
            "description": (
                f"Модель прогнозирует {result['dip_count']} час(а) ниже порога. "
                f"Минимальный баланс: {worst['balance']}M в {worst['label']}. "
                f"Порог: {result['threshold']}M."
            ),
            "meta": f"Intraday Forecast · {result['dip_count']} дип(а) · min={worst['balance']}M",
            "recommendation": (
                "Обеспечьте входящие платежи до 09:00 или перенесите крупные исходящие на послеобеденное время."
            ),
            "details": [
                ["Метод", "Intraday Liquidity Forecasting"],
                ["Счёт", f"{risky['currency']}/{risky['bank']}"],
                ["Дипов", str(result["dip_count"])],
                ["Мин. баланс", f"{worst['balance']}M в {worst['label']}"],
                ["Порог (10%)", f"{result['threshold']}M"],
                ["Суточная позиция", f"{result['daily_net']}M нетто"],
            ],
        }
    ]


def _build_rebalance_needed_alert(accounts: list[dict], cashflow: dict) -> list[dict]:
    """Alerts when rebalancing engine finds urgent unmatched deficits."""
    from .optimization_engine import compute_rebalancing

    result = compute_rebalancing(accounts, cashflow)
    if result["deficits_found"] == 0:
        return []
    uncovered = result["deficits_found"] - result["deficits_covered"]
    severity = "danger" if uncovered > 0 else "warning"
    return [
        {
            "id": "alert-rebalance-needed",
            "severity": severity,
            "title": f"Требуется перебалансировка — {result['deficits_found']} дефицит(а)",
            "description": (
                f"Выявлено {result['deficits_found']} счёт(а) с дефицитом ликвидности. "
                f"Покрыто: {result['deficits_covered']}, не покрыто: {uncovered}. "
                f"Рекомендуется переместить {result['total_moved']}M."
            ),
            "meta": f"Smart Rebalancing · {len(result['transfers'])} перевод(а) · стоимость ${result['total_cost_usd'] * 1000:.0f}",
            "recommendation": result["summary"],
            "details": [
                ["Метод", "Smart Rebalancing (greedy DCR/ERR matching)"],
                ["Дефицитов", str(result["deficits_found"])],
                ["Покрыто", str(result["deficits_covered"])],
                ["Не покрыто", str(uncovered)],
                ["К перемещению", f"{result['total_moved']}M"],
                ["Переводов", str(len(result["transfers"]))],
                ["Стоимость (оценка)", f"~${result['total_cost_usd'] * 1000:.0f}"],
            ],
        }
    ]


def _merge_dynamic_alerts(static_alerts: list[dict], data: dict) -> list[dict]:
    """
    Runs all analytics engines and merges with static alerts.
    Dynamic alerts are always recomputed; static ones kept as-is.
    """
    base = [
        a
        for a in static_alerts
        if a["id"] not in _DYNAMIC_IDS and not a["id"].startswith(_CLEARING_PREFIX)
    ]

    dynamic: list[dict] = []
    dynamic += _build_anomaly_alerts(data["cashflow"])
    dynamic += _build_distribution_alert(data["accounts"])
    dynamic += _build_clearing_gap_alerts(data["accounts"], data["forecast"])
    dynamic += _build_excess_reserve_alerts(data["accounts"])
    # New module alerts
    dynamic += _build_reserve_level_alert(data["accounts"], data["cashflow"])
    dynamic += _build_settlement_delay_alert(data["cashflow"])
    dynamic += _build_intraday_dip_alert(data["accounts"], data["cashflow"])
    dynamic += _build_rebalance_needed_alert(data["accounts"], data["cashflow"])

    # Sort: danger first, then warning, then ok/info
    order = {"danger": 0, "warning": 1, "info": 2, "ok": 3}
    merged = sorted(base + dynamic, key=lambda a: order.get(a["severity"], 9))
    return merged


# ── Optimization engine ────────────────────────────────────────────────────────


def get_optimization_plan() -> dict:
    """
    Returns a full optimization plan without applying it:
    rebalancing transfers + reserve release instructions + scenario summary.
    Used by the frontend to show the confirmation modal with rich detail.
    """
    from .optimization_engine import compute_rebalancing, compute_reserve_optimization

    data = get_dashboard()
    rebal = compute_rebalancing(data["accounts"], data["cashflow"])
    reserve_opt = compute_reserve_optimization(data["accounts"], data["cashflow"])

    # Build unified instruction list
    instructions: list[dict] = []

    # 1. Transfer instructions from rebalancing
    for t in rebal["transfers"]:
        instructions.append(
            {
                "type": "transfer",
                "priority": t["priority"],
                "label": t["label"],
                "amount": t["amount"],
                "currency": t["from_currency"],
                "channel": t["channel"],
                "lag_days": t["settlement_lag_days"],
                "cost_usd": t["estimated_cost_usd"],
                "urgency": t["urgency"],
                "rationale": t["rationale"],
            }
        )

    # 2. Reserve release instructions
    for inst in reserve_opt["instructions"]:
        instructions.append(
            {
                "type": "release",
                "priority": inst["priority"] + len(rebal["transfers"]),
                "label": inst["label"],
                "amount": inst["amount"],
                "currency": inst["currency"],
                "channel": "Внутренние",
                "lag_days": 0,
                "cost_usd": 0.0,
                "urgency": "normal",
                "rationale": inst["rationale"],
            }
        )

    instructions.sort(key=lambda x: (x["priority"], -x["amount"]))

    total_moved = round(sum(i["amount"] for i in instructions), 2)
    total_cost = round(sum(i["cost_usd"] for i in instructions), 4)
    frozen_before = data["summary"]["frozen_reserves"]["value"]
    frozen_after = round(
        max(0, frozen_before - reserve_opt["portfolio"]["total_potential_release"]), 2
    )

    return {
        "instructions": instructions,
        "transfers_count": len(rebal["transfers"]),
        "releases_count": len(reserve_opt["instructions"]),
        "total_moved": total_moved,
        "total_cost_usd": total_cost,
        "frozen_before": frozen_before,
        "frozen_after": frozen_after,
        "capital_freed": round(frozen_before - frozen_after, 2),
        "summary": (
            f"{len(instructions)} действий · "
            f"{total_moved}M перераспределено · "
            f"высвобождается ~{round(frozen_before - frozen_after, 2)}M замороженного капитала"
        ),
        # Legacy fields for frontend compat
        "steps": _state["optimization"]["steps"],
        "impact": _state["optimization"]["impact"],
    }


def apply_optimization() -> dict:
    """Apply the plan and mutate state. Returns enriched impact."""
    global _state

    plan = get_optimization_plan()
    impact = _state["optimization"]["impact"]

    # Apply EUR account fix (main critical transfer)
    for acc in _state["accounts"]:
        if acc["id"] == "eur":
            acc["status"] = "ok"
            acc["balance"] = 1.9
            acc["fill_pct"] = 64
            acc["note"] = "Баланс восстановлен после оптимизации"

    # Partially apply reserve releases to other ok accounts
    for acc in _state["accounts"]:
        if acc["id"] in ("chf", "usd") and acc["fill_pct"] > 75:
            acc["fill_pct"] = max(65, acc["fill_pct"] - 10)

    # Resolve EUR alert
    for alert in _state["alerts"]:
        if alert["id"] == "alert-eur":
            alert["severity"] = "ok"
            alert["title"] = "EUR / Barclays — разрыв устранён"
            alert["description"] = (
                "Перевод $1.3M из USD/JPMorgan выполнен. Остаток €1.9M покрывает обязательства."
            )
            alert["meta"] = "Оптимизация применена"

    _state["summary"]["frozen_reserves"]["value"] = impact["frozen_after"]

    # Return enriched impact with all instructions
    return {
        **impact,
        "instructions": plan["instructions"],
        "total_moved": plan["total_moved"],
        "capital_freed": plan["capital_freed"],
        "summary": plan["summary"],
    }


# ── Stress scenario ────────────────────────────────────────────────────────────


def get_scenario(key: ScenarioKey) -> dict:
    sc = _state.get("stress_scenarios", {}).get(key.value)
    if not sc:
        raise KeyError(f"Scenario '{key}' not found")
    return sc


# ── Filtered queries ───────────────────────────────────────────────────────────


def get_accounts(status_filter: str | None = None) -> list[dict]:
    accounts = copy.deepcopy(_state["accounts"])
    if status_filter and status_filter != "all":
        accounts = [a for a in accounts if a["status"] == status_filter]
    return accounts


def get_alerts(severity_filter: str | None = None) -> list[dict]:
    data = get_dashboard()
    alerts = data["alerts"]
    if severity_filter and severity_filter != "all":
        alerts = [a for a in alerts if a["severity"] == severity_filter]
    return alerts


# ── Search ─────────────────────────────────────────────────────────────────────


def search(query: str) -> list[dict]:
    q = query.lower()
    results = []
    data = get_dashboard()

    for acc in data["accounts"]:
        if (
            q
            in f"{acc['currency']} {acc['bank']} {acc['balance']} {acc['note']}".lower()
        ):
            results.append(
                {
                    "type": "account",
                    "title": f"{acc['currency']} / {acc['bank']}",
                    "sub": f"Остаток {acc['balance']}M · {acc['note']}",
                    "target": acc["id"],
                }
            )

    for alert in data["alerts"]:
        if (
            q
            in f"{alert['title']} {alert['description']} {alert.get('meta', '')}".lower()
        ):
            results.append(
                {
                    "type": "alert",
                    "title": alert["title"],
                    "sub": alert["description"][:80] + "…",
                    "target": alert["id"],
                }
            )

    for key, sc in _state.get("stress_scenarios", {}).items():
        if q in f"{sc['label']} {' '.join(sc['lines'])}".lower():
            results.append(
                {
                    "type": "scenario",
                    "title": f"Сценарий: {sc['label']}",
                    "sub": sc["lines"][0] if sc["lines"] else "",
                    "target": key,
                }
            )

    return results
