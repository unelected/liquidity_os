# LiquidityOS

**Система предиктивного управления ликвидностью для финтех-компаний и необанков.**

Решает пять ключевых проблем казначейства: неэффективное распределение резервов, кассовые разрывы из-за клиринговых задержек, отсутствие внутридневного прогноза, реактивное (а не предиктивное) управление и замороженный капитал в профицитных счетах.

---

## Быстрый старт

### Требования

- Python 3.11+
- pip

### Установка и запуск

```bash
# 1. Распакуйте архив и перейдите в папку проекта
cd liquidity_os

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Запустите сервер
uvicorn main:app --reload --port 8000
```

После запуска откройте в браузере:

| URL | Описание |
|-----|----------|
| http://localhost:8000 | Интерфейс (фронтенд) |
| http://localhost:8000/docs | Swagger UI — интерактивная документация API |
| http://localhost:8000/redoc | ReDoc — альтернативная документация |
| http://localhost:8000/api/health | Проверка состояния сервера |

### Офлайн-режим

Если бэкенд недоступен, фронтенд автоматически переключается в офлайн-режим:
показывает жёлтый баннер и работает на демонстрационных данных из `frontend/js/data.js`.
Все клиентские функции (поиск, фильтры, аналитика, экспорт CSV) продолжают работать.

---

## Структура проекта

```
liquidity_os/
│
├── main.py                                # Точка входа FastAPI-приложения
├── requirements.txt                       # Python-зависимости
├── README.md
│
├── backend/
│   ├── core/
│   │   ├── security.py                    # Rate limiting, CORS, санитизация, заголовки
│   │   └── seed_data.py                   # Дефолтный датасет (используется без БД)
│   │
│   ├── models/
│   │   └── schemas.py                     # Pydantic-схемы: валидация всех входов и выходов
│   │
│   ├── routers/
│   │   ├── dashboard.py                   # GET /api/dashboard, /api/accounts, /api/cashflow/anomalies
│   │   ├── alerts.py                      # GET /api/alerts, /api/alerts/{id}
│   │   ├── optimization.py                # POST /api/optimize, GET /api/optimize/plan,
│   │   │                                  #   /api/reserve, /api/settlement, /api/intraday,
│   │   │                                  #   /api/rebalance, POST /api/simulate
│   │   └── search.py                      # GET /api/search?q=...
│   │
│   └── services/
│       ├── liquidity_service.py           # Бизнес-логика: риск-скоринг, алерты, оптимизация
│       └── optimization_engine.py         # Пять аналитических движков (см. ниже)
│
└── frontend/
    ├── index.html                         # SPA-интерфейс (три вкладки)
    ├── css/
    │   └── style.css                      # Тёмная деловая тема
    └── js/
        ├── data.js                        # API-слой: fetch + офлайн-фоллбэк + клиентская аналитика
        ├── app.js                         # Оркестратор: состояние, вкладки, модалы
        ├── ui.js                          # Рендеринг DOM: все визуальные компоненты
        └── search.js                      # Клиентский поиск, фильтры, CSV-экспорт
```

---

## Аналитические движки

Все расчёты реализованы детерминированными статистическими методами — без ML и внешних зависимостей.

### 1. Weighted Risk Score — общий риск портфеля

**Где:** `liquidity_service.py → _compute_gap_risk()`

Каждый счёт получает очки по формуле:

```
score = (1 - fill_pct / 100) × severity_weight
```

Веса: `danger = 3.0`, `warning = 1.5`, `ok = 0.0`.
Сумма по портфелю → `low / medium / high`.

---

### 2. Z-score — аномалии транзакций

**Где:** `liquidity_service.py → detect_cashflow_anomalies()`

```
z = |x - μ| / σ
```

Порог: **1.8σ** (предупреждение) и **2.5σ** (критично).
Рассчитывается отдельно для inflow и outflow по скользящему окну 7 дней.

---

### 3. Days Coverage Ratio — кассовые разрывы

**Где:** `liquidity_service.py → _build_clearing_gap_alerts()`

```
DCR = balance / avg_daily_obligations
```

Если DCR меньше максимального клирингового лага (SWIFT = 3 дня), счёт помечается как рисковый.
Применяется стандартный банковский подход: лаги SEPA = 1д, SWIFT = 3д, карты = 5д.

---

### 4. Gini Coefficient — неэффективное распределение

**Где:** `liquidity_service.py → _gini()`

Коэффициент неравномерности распределения балансов по счетам.
`0` = идеально равномерно, `1` = весь капитал на одном счёте.
Порог предупреждения: **0.45**, критический: **0.60**.

---

### 5. Excess Reserve Ratio — избыточные резервы

**Где:** `liquidity_service.py → _build_excess_reserve_alerts()`

```
ERR = (balance - min_reserve) / balance
```

Порог предупреждения: **55%**, критический: **75%**.
Также считается портфельный ERR по всем счетам.

---

### 6. Reserve Optimization Engine

**Где:** `optimization_engine.py → compute_reserve_optimization()`

```
optimal_reserve = avg_daily_outflow × max_clearing_lag × safety_factor (1.25)
excess          = balance − optimal_reserve
potential_release = excess × 0.80
```

Рассчитывается доля каждого счёта в портфеле, оптимальный резерв масштабируется пропорционально. 20% избытка остаётся как дискреционный буфер.

---

### 7. Settlement Delay Forecasting — прогноз задержек

**Где:** `optimization_engine.py → forecast_settlement_delays()`

Таблица исторических P50/P95 задержек по каждому каналу, умноженная на коэффициент дня недели:

| Канал | P50 | P95 |
|-------|-----|-----|
| Внутренние | 0.1ч | 0.5ч |
| SEPA | 4ч | 20ч |
| SWIFT | 28ч | 60ч |
| Карты | 72ч | 110ч |

Пятница × 1.3, суббота × 1.8, воскресенье × 1.9.
Если P95 > 48ч — генерируется алерт.

---

### 8. Intraday Liquidity Forecasting — внутридневной прогноз

**Где:** `optimization_engine.py → forecast_intraday()`

Дневной объём inflow/outflow распределяется по 24 часам через вектор весов платёжной активности (утренний пик 09-11, послеобеденный 14-15, EOD-всплеск 16-17). Строится почасовая кривая баланса. Часы ниже 10% от открывающего баланса — "дип", генерирует алерт.

---

### 9. Smart Rebalancing — умное перебалансирование

**Где:** `optimization_engine.py → compute_rebalancing()`

Жадный алгоритм:

1. Классифицировать счета: дефицит (DCR < 3) или профицит (ERR > 40%)
2. Отсортировать дефициты по срочности (lowest DCR first)
3. Отсортировать профициты по доступности (highest excess first)
4. Жадно сопоставлять: `transfer = min(deficit_need, surplus_available)`
5. Выбрать оптимальный канал (SEPA для EUR, SWIFT для межвалютных)
6. Рассчитать стоимость перевода в bps

---

### 10. Scenario Simulation — стресс-тестирование

**Где:** `optimization_engine.py → simulate_scenario()`

Параметрические шоки применяются к текущему состоянию:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `volume_mult` | Множитель объёма платежей | `2.0` = объём ×2 |
| `delay_add_days` | Доп. дни задержки клиринга | `3` = +3 дня |
| `bank_unavailable` | ID счёта для отключения | `"eur"` |
| `fx_shock_pct` | Курсовой шок EUR-счетов | `-5.0` = −5% |
| `holiday_days` | Праздничные дни | `2` |

После применения шоков пересчитывается риск-скор, проверяется достаточность резервов и генерируются конкретные инструкции к действию.

---

## API — полный справочник

### Общее

Все эндпоинты возвращают JSON. Базовый URL: `http://localhost:8000/api`.

### Дашборд

```
GET  /api/health
     → { status, version }

GET  /api/dashboard
     → { summary, accounts, alerts, cashflow, forecast,
         clearing_delays, optimization, stress_scenarios }

GET  /api/accounts?status=ok|warning|danger
     → { accounts: [...] }

GET  /api/cashflow/anomalies
     → { anomalies: [...], count }
```

### Алерты

```
GET  /api/alerts?severity=danger|warning|ok|info
     → { alerts: [...] }

GET  /api/alerts/{alert_id}
     → { id, severity, title, description, details, ... }
```

### Оптимизация

```
GET  /api/optimize/plan
     → { instructions, total_moved, capital_freed,
         frozen_before, frozen_after, summary }

POST /api/optimize
     Body: { "confirm": true }
     → { ok, impact: { frozen_after, saved_total, risk_after, ... } }
```

### Аналитические модули

```
GET  /api/reserve
     → { per_account: [...], portfolio: {...}, instructions: [...] }

GET  /api/settlement?day_of_week=0..6&holiday_penalty_h=0..72
     → { rails: [...], fastest_rail, slowest_rail, recommendations }

GET  /api/intraday?account_id=usd&threshold_pct=0.10
     → { hours: [...], dips: [...], worst_dip, dip_count, daily_net }

GET  /api/rebalance
     → { transfers: [...], total_moved, total_cost_usd, summary }

POST /api/simulate
     Body: {
       "volume_mult": 2.0,
       "delay_add_days": 3,
       "bank_unavailable": "eur",
       "fx_shock_pct": -5.0,
       "holiday_days": 1
     }
     → { applied_shocks, before, after, impact, instructions }
```

### Поиск

```
GET  /api/search?q=barclays
     → { results: [{ type, title, sub, target }], total }
```

### Пре-заданные сценарии

```
GET  /api/scenario/swift|volume|holiday|fx
POST /api/scenario  Body: { "scenario": "swift" }
     → { label, severity, lines }
```

---

## Алерты — полный список

Алерты вычисляются автоматически при каждом обращении к `/api/dashboard`. Статические алерты хранятся в `seed_data.py`, динамические пересчитываются в реальном времени.

| ID | Метод | Условие |
|----|-------|---------|
| `alert-eur` | Статический | EUR/Barclays дефицит |
| `alert-swift` | Статический | Задержка SWIFT |
| `alert-gbp` | Статический | GBP нормализован |
| `alert-anomaly-txn` | Z-score | z > 1.8σ в inflow/outflow |
| `alert-distribution` | Gini | Gini > 0.45 |
| `alert-clearing-{id}` | DCR | DCR < 2 дней |
| `alert-excess-reserves` | ERR | ERR > 55% |
| `alert-reserve-suboptimal` | Reserve Engine | Эффективность < 85% |
| `alert-settlement-delay` | Settlement Forecast | P95 > 48ч сегодня |
| `alert-intraday-dip` | Intraday Forecast | Баланс < 10% порога |
| `alert-rebalance-needed` | Smart Rebalancing | Есть непокрытые дефициты |

---

## Безопасность

| Механизм | Реализация |
|----------|------------|
| Rate limiting | 60 req/min (API), 30/min (поиск), 10/min (оптимизация) — per IP, sliding window |
| CORS | Whitelist в `backend/core/security.py → ALLOWED_ORIGINS` |
| Валидация входных данных | Pydantic v2 — все типы, диапазоны, длины строк |
| Санитизация строк | Блокировка `< > " ' % ; ( ) & +` в поисковых запросах |
| Security headers | X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Cache-Control |
| Обработка ошибок | Глобальный exception handler, никаких stack trace в ответах |

---

## Примеры запросов (curl)

```bash
# Полный дашборд
curl http://localhost:8000/api/dashboard | python3 -m json.tool

# Только критичные алерты
curl "http://localhost:8000/api/alerts?severity=danger"

# Оптимальные резервы
curl http://localhost:8000/api/reserve

# Прогноз задержек на пятницу
curl "http://localhost:8000/api/settlement?day_of_week=4"

# Внутридневной прогноз для EUR-счёта
curl "http://localhost:8000/api/intraday?account_id=eur&threshold_pct=0.15"

# Рекомендации по перебалансированию
curl http://localhost:8000/api/rebalance

# Стресс-тест: SWIFT +3 дня + объём ×1.5
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"volume_mult": 1.5, "delay_add_days": 3}'

# Стресс-тест: отключение EUR-счёта
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"bank_unavailable": "eur"}'

# Применить оптимизацию
curl -X POST http://localhost:8000/api/optimize \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'

# Поиск
curl "http://localhost:8000/api/search?q=barclays"
```

---

## Подключение реальной базы данных

Все операции с данными сосредоточены в `backend/services/liquidity_service.py`.
В-memory состояние `_state` заменяется на SQLAlchemy-сессию или любой async ORM —
публичные сигнатуры функций остаются неизменными.

```python
# Пример замены get_dashboard() для работы с БД:
async def get_dashboard(db: AsyncSession) -> dict:
    accounts = await db.execute(select(Account))
    ...
```

---

## Зависимости

```
fastapi==0.115.5       — веб-фреймворк
uvicorn[standard]==0.32.0  — ASGI-сервер
pydantic==2.9.2        — валидация данных
python-multipart==0.0.12   — поддержка form-data
```

Внешних ML-библиотек нет. Все аналитические расчёты реализованы на стандартной библиотеке Python.
