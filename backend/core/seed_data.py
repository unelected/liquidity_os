"""
seed_data.py — Default dataset used when no database is connected.
Mirrors the shape of DashboardResponse exactly.
"""

from __future__ import annotations

SEED: dict = {
    "summary": {
        "total_liquidity": {"value": 47.2, "currency": "USD", "unit": "M"},
        "frozen_reserves": {"value": 9.4,  "currency": "USD", "unit": "M", "prev": 15.0},
        "gap_risk":        {"level": "medium", "label": "Средний", "accounts_at_risk": 1},
        "overdrafts_30d":  {"value": 12000, "currency": "USD", "change_pct": -91},
    },

    "accounts": [
        {
            "id": "usd", "currency": "USD", "bank": "JPMorgan",
            "balance": 18.4, "balance_unit": "M", "min_reserve": 2.0,
            "fill_pct": 88, "status": "ok",
            "incoming": "$5.1M (SWIFT, 2 дня)",
            "outgoing": "$3.2M",
            "note": "Банковский праздник 27 мая (+1 день к SWIFT)",
        },
        {
            "id": "eur", "currency": "EUR", "bank": "Barclays",
            "balance": 0.6, "balance_unit": "M", "min_reserve": 1.5,
            "fill_pct": 12, "status": "danger",
            "incoming": "€0.6M (SEPA, чт 23:00)",
            "outgoing": "€1.8M",
            "note": "Дефицит €1.2M — риск разрыва в пятницу",
        },
        {
            "id": "gbp", "currency": "GBP", "bank": "HSBC",
            "balance": 2.4, "balance_unit": "M", "min_reserve": 1.0,
            "fill_pct": 55, "status": "warning",
            "incoming": "£890K (карты)",
            "outgoing": "£0.9M",
            "note": "Покрытие на 7 дней",
        },
        {
            "id": "chf", "currency": "CHF", "bank": "UBS",
            "balance": 3.1, "balance_unit": "M", "min_reserve": 0.8,
            "fill_pct": 72, "status": "ok",
            "incoming": "CHF 0.5M",
            "outgoing": "CHF 1.2M",
            "note": "Избыток CHF 0.8M — можно высвободить",
        },
        {
            "id": "aed", "currency": "AED", "bank": "Emirates NBD",
            "balance": 4.8, "balance_unit": "M", "min_reserve": 3.0,
            "fill_pct": 40, "status": "warning",
            "incoming": "AED 1.1M",
            "outgoing": "AED 2.1M",
            "note": "Мониторинг — буфер снижается",
        },
    ],

    "alerts": [
        {
            "id": "alert-eur",
            "severity": "danger",
            "title": "Риск кассового разрыва — EUR / Barclays",
            "description": "Выплаты мерчантам €1.8M в пятницу. Текущий остаток €0.6M. SEPA-поступление ожидается в четверг — за 6 часов до дедлайна.",
            "meta": "2 дня до критической точки",
            "recommendation": "Перевод €1.3M с USD/JPMorgan",
            "details": [
                ["Тип",             "Кассовый разрыв"],
                ["Счёт",            "EUR / Barclays"],
                ["Дедлайн",         "Пятница, 10:00"],
                ["Обязательства",   "€1.8M (выплаты мерчантам)"],
                ["Текущий остаток", "€0.6M"],
                ["Ожидаемое SEPA",  "€0.6M — чт 23:00"],
                ["Дефицит",         "€1.2M"],
                ["Рекомендация",    "Перевод €1.3M с USD/JPMorgan"],
                ["Приоритет",       "Критический"],
            ],
        },
        {
            "id": "alert-swift",
            "severity": "warning",
            "title": "Задержка SWIFT — входящий USD $2.1M",
            "description": "Перевод от Bank of America задержан на +1 день из-за праздника в США (27 мая).",
            "meta": "Задержка +1 день · USD/JPMorgan",
            "recommendation": "Буфер на USD достаточен, действий не требуется",
            "details": [
                ["Тип",         "Задержка расчётов"],
                ["Счёт",        "USD / JPMorgan"],
                ["Отправитель", "Bank of America"],
                ["Сумма",       "$2.1M"],
                ["Исх. дата",   "27 мая"],
                ["Нов. дата",   "28 мая"],
                ["Причина",     "Memorial Day (США)"],
                ["Влияние",     "Минимальное"],
                ["Рекомендация","Действий не требуется"],
            ],
        },
        {
            "id": "alert-gbp",
            "severity": "ok",
            "title": "GBP / HSBC — баланс нормализован",
            "description": "Карточный клиринг £890K поступил. Остаток £2.4M покрывает обязательства на 7 дней.",
            "meta": "Обновлено сегодня · риск устранён",
            "recommendation": None,
            "details": [
                ["Счёт",      "GBP / HSBC"],
                ["Поступило", "£890K (карты)"],
                ["Остаток",   "£2.4M"],
                ["Покрытие",  "7 дней обязательств"],
                ["Статус",    "Норма"],
            ],
        },
    ],

    "cashflow": {
        "days":    ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
        "inflow":  [8.2, 6.5, 11.3, 9.8, 14.1, 4.2, 7.6],
        "outflow": [7.1, 7.8,  9.2, 8.4, 12.3, 3.8, 6.9],
    },

    "forecast": [
        {"days_ahead": 1, "obligations": "€1.8M", "incoming": "€0.6M",  "channel": "SEPA",  "ok": False},
        {"days_ahead": 2, "obligations": "$3.2M", "incoming": "$5.1M",  "channel": "SWIFT", "ok": True},
        {"days_ahead": 3, "obligations": "£0.9M", "incoming": "£1.2M",  "channel": "Карты", "ok": True},
        {"days_ahead": 4, "obligations": "$2.5M", "incoming": "$2.3M",  "channel": "SEPA",  "ok": False},
        {"days_ahead": 5, "obligations": "$1.8M", "incoming": "$4.0M",  "channel": "SWIFT", "ok": True},
    ],

    "clearing_delays": [
        {"system": "SEPA",        "delay": "до 1 дня",    "notes": "Внутри ЕС"},
        {"system": "SWIFT",       "delay": "2–3 дня",     "notes": "Межбанк, международные"},
        {"system": "Карты",       "delay": "до 5 дней",   "notes": "Visa / Mastercard клиринг"},
        {"system": "Внутренние",  "delay": "моментально", "notes": "Внутри платформы"},
    ],

    "optimization": {
        "steps": [
            {"from": "USD / JPMorgan",     "to": "EUR / Barclays", "amount": "+€1.3M"},
            {"from": "AED / Emirates NBD", "to": "GBP / HSBC",     "amount": "+$0.4M"},
            {"from": "CHF / UBS (резерв)", "to": "Высвобождение",  "amount": "−$0.8M замороженных"},
        ],
        "impact": {
            "frozen_after":     8.6,
            "saved_total":      6.4,
            "risk_after":       "low",
            "risk_after_label": "Низкий",
            "alerts_resolved":  1,
        },
    },

    "stress_scenarios": {
        "swift": {
            "label": "SWIFT задержка +3 дня",
            "severity": "warning",
            "lines": [
                "Заморожено: $5.3M на 3 счетах.",
                "Риск разрыва: ВЫСОКИЙ — EUR, AED.",
                "Рекомендация: кредитная линия CHF на €2M.",
                "Потери без действий: ~$45K.",
            ],
        },
        "volume": {
            "label": "Объём транзакций ×2",
            "severity": "warning",
            "lines": [
                "Потребность в ликвидности: $62M.",
                "Дефицит: $14.8M.",
                "Рекомендация: резервы CHF + AED + O/N лимит.",
            ],
        },
        "holiday": {
            "label": "Банковский праздник EU",
            "severity": "info",
            "lines": [
                "SEPA заморожено на 1 день (28 мая).",
                "Затронуто: €3.1M.",
                "Уведомление treasury за 48 часов.",
                "Рекомендация: буфер €1.5M в среду.",
            ],
        },
        "fx": {
            "label": "EUR/USD −5%",
            "severity": "danger",
            "lines": [
                "EUR-остатки в USD упали на $0.8M.",
                "Реальная ликвидность: $46.4M.",
                "Рекомендация: EUR/USD форвард €2M @ 1.082.",
                "Потери без хеджа: ~$120K/мес.",
            ],
        },
    },
}
