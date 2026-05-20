// data.js — Frontend data / API layer
// Calls FastAPI at API_BASE; on failure falls back to DEFAULT_DATA (offline mode).
// Snake_case from backend is normalised to camelCase here so the rest of the
// frontend never needs to worry about it.

const API_BASE = 'http://localhost:8000/api';

// ── Default offline data (mirrors backend seed_data.py) ───────────────────────
export const DEFAULT_DATA = {
  summary: {
    totalLiquidity:  { value: 47.2, currency: 'USD', unit: 'M' },
    frozenReserves:  { value: 9.4,  currency: 'USD', unit: 'M', prev: 15.0 },
    gapRisk:         { level: 'medium', label: 'Средний', accountsAtRisk: 1 },
    overdrafts30d:   { value: 12000, currency: 'USD', changePct: -91 },
  },
  accounts: [
    { id:'usd', currency:'USD', bank:'JPMorgan',     balance:18.4, balanceUnit:'M', minReserve:2.0,  fillPct:88, status:'ok',      incoming:'$5.1M (SWIFT, 2 дня)',    outgoing:'$3.2M',    note:'Банковский праздник 27 мая (+1 день к SWIFT)' },
    { id:'eur', currency:'EUR', bank:'Barclays',     balance:0.6,  balanceUnit:'M', minReserve:1.5,  fillPct:12, status:'danger',   incoming:'€0.6M (SEPA, чт 23:00)', outgoing:'€1.8M',    note:'Дефицит €1.2M — риск разрыва в пятницу' },
    { id:'gbp', currency:'GBP', bank:'HSBC',         balance:2.4,  balanceUnit:'M', minReserve:1.0,  fillPct:55, status:'warning',  incoming:'£890K (карты)',           outgoing:'£0.9M',    note:'Покрытие на 7 дней' },
    { id:'chf', currency:'CHF', bank:'UBS',          balance:3.1,  balanceUnit:'M', minReserve:0.8,  fillPct:72, status:'ok',       incoming:'CHF 0.5M',               outgoing:'CHF 1.2M', note:'Избыток CHF 0.8M — можно высвободить' },
    { id:'aed', currency:'AED', bank:'Emirates NBD', balance:4.8,  balanceUnit:'M', minReserve:3.0,  fillPct:40, status:'warning',  incoming:'AED 1.1M',               outgoing:'AED 2.1M', note:'Мониторинг — буфер снижается' },
  ],
  alerts: [
    {
      id:'alert-eur', severity:'danger',
      title:'Риск кассового разрыва — EUR / Barclays',
      description:'Выплаты мерчантам €1.8M в пятницу. Текущий остаток €0.6M. SEPA-поступление ожидается в четверг — за 6 часов до дедлайна.',
      meta:'2 дня до критической точки', recommendation:'Перевод €1.3M с USD/JPMorgan',
      details:[['Тип','Кассовый разрыв'],['Счёт','EUR / Barclays'],['Дедлайн','Пятница, 10:00'],['Обязательства','€1.8M'],['Текущий остаток','€0.6M'],['Ожидаемое SEPA','€0.6M — чт 23:00'],['Дефицит','€1.2M'],['Рекомендация','Перевод €1.3M с USD/JPMorgan'],['Приоритет','Критический']],
    },
    {
      id:'alert-swift', severity:'warning',
      title:'Задержка SWIFT — входящий USD $2.1M',
      description:'Перевод от Bank of America задержан на +1 день из-за праздника в США (27 мая).',
      meta:'Задержка +1 день · USD/JPMorgan', recommendation:'Буфер на USD достаточен, действий не требуется',
      details:[['Тип','Задержка расчётов'],['Счёт','USD / JPMorgan'],['Отправитель','Bank of America'],['Сумма','$2.1M'],['Исх. дата','27 мая'],['Нов. дата','28 мая'],['Причина','Memorial Day (США)'],['Влияние','Минимальное'],['Рекомендация','Действий не требуется']],
    },
    {
      id:'alert-gbp', severity:'ok',
      title:'GBP / HSBC — баланс нормализован',
      description:'Карточный клиринг £890K поступил. Остаток £2.4M покрывает обязательства на 7 дней.',
      meta:'Обновлено сегодня · риск устранён', recommendation:null, details:[['Счёт','GBP / HSBC'],['Поступило','£890K (карты)'],['Остаток','£2.4M'],['Покрытие','7 дней обязательств'],['Статус','Норма']],
    },
  ],
  cashflow: {
    days:['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],
    inflow: [8.2,6.5,11.3,9.8,14.1,4.2,7.6],
    outflow:[7.1,7.8, 9.2,8.4,12.3,3.8,6.9],
  },
  forecast: [
    {daysAhead:1, obligations:'€1.8M', incoming:'€0.6M', channel:'SEPA',  ok:false},
    {daysAhead:2, obligations:'$3.2M', incoming:'$5.1M', channel:'SWIFT', ok:true},
    {daysAhead:3, obligations:'£0.9M', incoming:'£1.2M', channel:'Карты', ok:true},
    {daysAhead:4, obligations:'$2.5M', incoming:'$2.3M', channel:'SEPA',  ok:false},
    {daysAhead:5, obligations:'$1.8M', incoming:'$4.0M', channel:'SWIFT', ok:true},
  ],
  clearingDelays: [
    {system:'SEPA',       delay:'до 1 дня',    notes:'Внутри ЕС'},
    {system:'SWIFT',      delay:'2–3 дня',     notes:'Межбанк, международные'},
    {system:'Карты',      delay:'до 5 дней',   notes:'Visa / Mastercard клиринг'},
    {system:'Внутренние', delay:'моментально', notes:'Внутри платформы'},
  ],
  optimization: {
    steps: [
      {from:'USD / JPMorgan',     to:'EUR / Barclays', amount:'+€1.3M'},
      {from:'AED / Emirates NBD', to:'GBP / HSBC',     amount:'+$0.4M'},
      {from:'CHF / UBS (резерв)', to:'Высвобождение',  amount:'−$0.8M замороженных'},
    ],
    impact: {
      frozenAfter:8.6, savedTotal:6.4,
      riskAfter:'low', riskAfterLabel:'Низкий', alertsResolved:1,
    },
  },
  stressScenarios: {
    swift:   {label:'SWIFT задержка +3 дня',   severity:'warning', lines:['Заморожено: $5.3M на 3 счетах.','Риск разрыва: ВЫСОКИЙ — EUR, AED.','Рекомендация: кредитная линия CHF на €2M.','Потери без действий: ~$45K.']},
    volume:  {label:'Объём транзакций ×2',      severity:'warning', lines:['Потребность в ликвидности: $62M.','Дефицит: $14.8M.','Рекомендация: резервы CHF + AED + O/N лимит.']},
    holiday: {label:'Банковский праздник EU',   severity:'info',    lines:['SEPA заморожено на 1 день (28 мая).','Затронуто: €3.1M.','Уведомление treasury за 48 часов.','Рекомендация: буфер €1.5M в среду.']},
    fx:      {label:'EUR/USD −5%',              severity:'danger',  lines:['EUR-остатки в USD упали на $0.8M.','Реальная ликвидность: $46.4M.','Рекомендация: EUR/USD форвард €2M @ 1.082.','Потери без хеджа: ~$120K/мес.']},
  },
};

// ── snake_case → camelCase normaliser ─────────────────────────────────────────
function normalise(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  if (Array.isArray(raw)) return raw.map(normalise);
  const out = {};
  for (const [k, v] of Object.entries(raw)) {
    const camel = k.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
    out[camel] = normalise(v);
  }
  return out;
}

// ── Fetch helper ───────────────────────────────────────────────────────────────
async function apiFetch(endpoint, opts = {}) {
  const res = await fetch(API_BASE + endpoint, {
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(5000),
    ...opts,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return normalise(await res.json());
}

// ── Public API ─────────────────────────────────────────────────────────────────
export async function loadData() {
  try {
    const data = await apiFetch('/dashboard');
    return { data, offline: false };
  } catch {
    return { data: DEFAULT_DATA, offline: true };
  }
}

export async function postOptimize() {
  try {
    const data = await apiFetch('/optimize', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    });
    return { ok: true, offline: false, data };
  } catch {
    return { ok: false, offline: true, data: DEFAULT_DATA.optimization };
  }
}

export async function serverSearch(query) {
  try {
    const data = await apiFetch(`/search?q=${encodeURIComponent(query)}`);
    return { results: data.results || [], offline: false };
  } catch {
    return { results: [], offline: true };
  }
}

// ── Client-side analytics (offline fallback mirrors backend logic) ─────────────
// Same four methods as liquidity_service.py — runs in browser when offline.

const ANOMALY_Z = 1.8;
const GINI_WARN = 0.45, GINI_DANGER = 0.60;
const ERR_WARN  = 0.55, ERR_DANGER  = 0.75;
const DCR_WARN  = 2.0,  DCR_DANGER  = 1.0;
const CLEARING_LAGS = { SEPA:1, SWIFT:3, 'Карты':5 };

function _mean(arr)  { return arr.reduce((a,b)=>a+b,0)/arr.length; }
function _std(arr,m) { return Math.sqrt(arr.reduce((a,x)=>a+(x-m)**2,0)/arr.length); }

function _gini(vals) {
  const n = vals.length, total = vals.reduce((a,b)=>a+b,0);
  if (!n || !total) return 0;
  const xs = [...vals].sort((a,b)=>a-b);
  const ws  = xs.reduce((acc,x,i)=>acc+(i+1)*x, 0);
  return Math.round(((2*ws)/(n*total) - (n+1)/n)*1000)/1000;
}

export function computeDynamicAlerts(data) {
  const alerts = [];

  // 1. Z-score anomaly
  for (const key of ['inflow','outflow']) {
    const s = data.cashflow[key];
    const m = _mean(s), sd = _std(s, m);
    if (!sd) continue;
    const worst = s.map((v,i)=>({v,i,z:Math.abs(v-m)/sd})).sort((a,b)=>b.z-a.z)[0];
    if (worst.z > ANOMALY_Z) {
      const dir  = key==='inflow' ? 'входящих' : 'исходящих';
      const dev  = Math.round((worst.v-m)/m*1000)/10;
      const sev  = worst.z > 2.5 ? 'danger' : 'warning';
      alerts.push({
        id:'alert-anomaly-txn', severity:sev,
        title:`Аномалия транзакций — ${data.cashflow.days[worst.i]} (${dir})`,
        description:`Объём ${dir} ${dev>0?'↑':'↓'}${Math.abs(dev)}% от нормы (${worst.v}M vs среднее ${Math.round(m*10)/10}M). Z-score: ${Math.round(worst.z*100)/100}σ.`,
        meta:`Z-score метод · порог ${ANOMALY_Z}σ`,
        recommendation:'Проверьте источник всплеска. Возможны ошибочные проводки.',
        details:[['Метод','Z-score'],['День',data.cashflow.days[worst.i]],['Серия',dir],['Значение',`${worst.v}M`],['Среднее (7д)',`${Math.round(m*10)/10}M`],['Отклонение',`${dev}%`],['Z-score',String(Math.round(worst.z*100)/100)]],
      });
      break;
    }
  }

  // 2. Gini — distribution
  const bals = data.accounts.map(a=>a.balance).filter(b=>b>0);
  const g = _gini(bals);
  if (g >= GINI_WARN) {
    const mx = data.accounts.reduce((a,b)=>b.balance>a.balance?b:a);
    const mn = data.accounts.reduce((a,b)=>b.balance<a.balance?b:a);
    const ratio = Math.round(mx.balance/Math.max(mn.balance,0.01)*10)/10;
    alerts.push({
      id:'alert-distribution', severity: g>=GINI_DANGER?'danger':'warning',
      title:'Неэффективное распределение средств между счетами',
      description:`Коэффициент Джини: ${g} (норма < ${GINI_WARN}). Дисбаланс ${mx.currency}/${mx.bank} превышает ${mn.currency}/${mn.bank} в ${ratio}x.`,
      meta:`Gini = ${g} · коэффициент концентрации балансов`,
      recommendation:`Перераспределите часть остатка с ${mx.currency}/${mx.bank} на дефицитные счета.`,
      details:[['Метод','Коэффициент Джини'],['Gini (факт)',String(g)],['Gini (норма)',`< ${GINI_WARN}`],['Макс. остаток',`${mx.balance}M (${mx.currency}/${mx.bank})`],['Мин. остаток',`${mn.balance}M (${mn.currency}/${mn.bank})`],['Дисбаланс',`${ratio}x`]],
    });
  }

  // 3. Days Coverage Ratio — clearing gaps
  const worstLag = Math.max(...Object.values(CLEARING_LAGS));
  const worstCh  = Object.entries(CLEARING_LAGS).find(([,v])=>v===worstLag)[0];
  for (const acc of data.accounts) {
    if (acc.balance<=0 || acc.minReserve<=0) continue;
    const avgDaily = acc.minReserve * 0.5;
    const dcr      = acc.balance / avgDaily;
    if (dcr >= DCR_WARN) continue;
    const sev = dcr < DCR_DANGER ? 'danger' : 'warning';
    alerts.push({
      id:`alert-clearing-${acc.id}`, severity:sev,
      title:`Риск кассового разрыва (клиринг) — ${acc.currency} / ${acc.bank}`,
      description:`DCR: ${Math.round(dcr*10)/10} дн. При задержке ${worstCh} (${worstLag} дн.) остаток ${acc.balance}M может не покрыть обязательства.`,
      meta:`DCR = ${Math.round(dcr*100)/100} · остаток ÷ среднедневные обязательства`,
      recommendation:`Пополните счёт минимум до ${Math.round(acc.minReserve*worstLag*10)/10}M для покрытия ${worstLag}-дневного лага.`,
      details:[['Метод','Days Coverage Ratio (DCR)'],['Счёт',`${acc.currency} / ${acc.bank}`],['Остаток',`${acc.balance}M`],['Мин. резерв',`${acc.minReserve}M`],['DCR',`${Math.round(dcr*100)/100} дн.`],['Лаг клиринга',`${worstLag} дн. (${worstCh})`]],
    });
  }

  // 4. Excess Reserve Ratio
  const totalBal = data.accounts.reduce((s,a)=>s+a.balance,0);
  const totalEx  = data.accounts.reduce((s,a)=>s+Math.max(0,a.balance-a.minReserve),0);
  const portERR  = totalBal ? totalEx/totalBal : 0;
  const worstAcc = data.accounts.filter(a=>a.balance>0&&a.minReserve>0)
    .map(a=>({...a, err:(a.balance-a.minReserve)/a.balance, excess:a.balance-a.minReserve}))
    .filter(a=>a.err>=ERR_WARN)
    .sort((a,b)=>b.err-a.err)[0];
  if (worstAcc) {
    alerts.push({
      id:'alert-excess-reserves', severity: worstAcc.err>=ERR_DANGER?'danger':'warning',
      title:'Избыточные резервы — капитал заморожен',
      description:`Общий избыток: ~${Math.round(totalEx*10)/10}M. Наибольший: ${worstAcc.currency}/${worstAcc.bank} — ERR ${Math.round(worstAcc.err*100)}% (остаток ${worstAcc.balance}M, мин. резерв ${worstAcc.minReserve}M). Портфельный ERR: ${Math.round(portERR*100)}%.`,
      meta:`ERR = ${Math.round(worstAcc.err*100)}% · (остаток − резерв) ÷ остаток`,
      recommendation:`Высвободите ~${Math.round(totalEx*10)/10}M из профицитных счетов.`,
      details:[['Метод','Excess Reserve Ratio (ERR)'],['Наибольший ERR',`${worstAcc.currency}/${worstAcc.bank}`],['ERR (факт)',`${Math.round(worstAcc.err*100)}%`],['ERR (порог)',`${ERR_WARN*100}%`],['Остаток',`${worstAcc.balance}M`],['Мин. резерв',`${worstAcc.minReserve}M`],['Избыток (счёт)',`${Math.round(worstAcc.excess*10)/10}M`],['Избыток (портфель)',`~${Math.round(totalEx*10)/10}M`]],
    });
  }

  // Sort: danger first
  const order = {danger:0,warning:1,info:2,ok:3};
  return alerts.sort((a,b)=>(order[a.severity]??9)-(order[b.severity]??9));
}
