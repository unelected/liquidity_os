// ui.js — DOM rendering functions

import { state } from './app.js';

export function qs(sel, ctx = document) { return ctx.querySelector(sel); }

function el(tag, cls, html = '') {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
}
function statusClass(s) { return { ok:'ok', warning:'warn', danger:'risk' }[s] || 'ok'; }
function statusLabel(s) { return { ok:'Норма', warning:'Низкий', danger:'Риск' }[s] || s; }
function sevClass(s)    { return { danger:'risk', warning:'warn', ok:'ok', info:'info' }[s] || 'ok'; }
function sevLabel(s)    { return { danger:'Критический', warning:'Внимание', ok:'Норма', info:'Инфо' }[s] || s; }

// ── Offline banner ─────────────────────────────────────────────────────────
export function renderOfflineBanner(show) {
  let b = qs('#offline-banner');
  if (!b) { b = el('div','offline-banner'); b.id='offline-banner'; document.body.prepend(b); }
  if (show) {
    b.innerHTML = `
      <span class="ob-icon">⚠</span>
      <span>Сеть недоступна — сайт работает в <strong>офлайн-режиме</strong>. Данные демонстрационные.</span>
      <button class="ob-retry" onclick="window.App.retryConnection()">Переподключиться</button>`;
    b.classList.add('show');
  } else { b.classList.remove('show'); }
}

// ── Summary ────────────────────────────────────────────────────────────────
export function renderSummary(s) {
  const { totalLiquidity, frozenReserves, gapRisk, overdrafts30d } = s;
  qs('#stat-liquidity').textContent = `$${totalLiquidity.value}M`;
  qs('#stat-frozen').textContent    = `$${frozenReserves.value}M`;
  qs('#stat-frozen-hint').textContent = `↓ с $${frozenReserves.prev}M — сэкономлено $${(frozenReserves.prev - frozenReserves.value).toFixed(1)}M`;

  const rv = qs('#stat-risk'), rh = qs('#stat-risk-hint');
  rv.textContent = gapRisk.label;
  if (gapRisk.level === 'low') {
    rv.className = 'stat-value ok'; rh.className = 'stat-hint ok';
    rh.textContent = 'Все счета в норме';
  } else if (gapRisk.level === 'medium') {
    rv.className = 'stat-value warn'; rh.className = 'stat-hint warn';
    rh.textContent = `${gapRisk.accountsAtRisk} счёт в зоне риска`;
  } else {
    rv.className = 'stat-value risk'; rh.className = 'stat-hint risk';
    rh.textContent = `${gapRisk.accountsAtRisk} счёт(а) в критической зоне`;
  }
  const sign = overdrafts30d.changePct < 0 ? '↓' : '↑';
  qs('#stat-overdraft').textContent      = `$${(overdrafts30d.value/1000).toFixed(0)}K`;
  qs('#stat-overdraft-hint').textContent = `${sign} ${Math.abs(overdrafts30d.changePct)}% к прошлому месяцу`;
}

// ── Accounts ───────────────────────────────────────────────────────────────
export function renderAccounts(accounts) {
  const tbody = qs('#accounts-tbody'); tbody.innerHTML = '';
  accounts.forEach(acc => {
    const sc = statusClass(acc.status), lbl = statusLabel(acc.status);
    const tr = el('tr','account-row'); tr.dataset.id = acc.id;
    tr.innerHTML = `
      <td class="td-currency">${acc.currency}</td>
      <td class="td-bank">${acc.bank}</td>
      <td class="td-mono">${acc.balance}${acc.balanceUnit} ${acc.currency}</td>
      <td><div class="progress-wrap"><div class="progress-fill ${sc}" style="width:${acc.fillPct}%"></div></div></td>
      <td><span class="status-badge ${sc}">${lbl}</span></td>`;
    tbody.appendChild(tr);
  });
}

// ── Alerts list ────────────────────────────────────────────────────────────
export function renderAlerts(alerts) {
  const c = qs('#alerts-list'); c.innerHTML = '';
  let count = 0;
  alerts.forEach(a => {
    if (a.severity !== 'ok') count++;
    const sc = sevClass(a.severity), div = el('div',`alert-row ${sc}`);
    div.dataset.id = a.id;
    div.innerHTML = `
      <span class="alert-dot ${sc}"></span>
      <div class="alert-body">
        <div class="alert-title">${a.title}</div>
        <div class="alert-desc">${a.description}</div>
        ${a.meta ? `<div class="alert-meta">${a.meta}</div>` : ''}
      </div>
      <span class="alert-chevron">›</span>`;
    c.appendChild(div);
  });
  const cnt = qs('#tab-alerts-count');
  cnt.textContent = count;
  cnt.style.display = count > 0 ? 'inline-flex' : 'none';
}

// ── Dashboard alert strip ──────────────────────────────────────────────────
export function renderDashboardAlerts(alerts) {
  const c = qs('#dash-alerts'); c.innerHTML = '';
  alerts.filter(a => a.severity !== 'ok').slice(0,3).forEach(a => {
    const sc = sevClass(a.severity), div = el('div',`dash-alert ${sc}`);
    div.dataset.id = a.id;
    div.innerHTML = `
      <span class="alert-dot ${sc}"></span>
      <div>
        <div class="dash-alert-title">${a.title}</div>
        <div class="dash-alert-rec">${a.recommendation || a.meta || ''}</div>
      </div>`;
    c.appendChild(div);
  });
}

// ── Chart (accepts target selector) ───────────────────────────────────────
export function renderChart(cashflow, selector) {
  const wrap = qs(selector); if (!wrap) return;
  wrap.innerHTML = '';
  const { days, inflow, outflow } = cashflow;
  const mx = Math.max(...inflow, ...outflow), H = 100;
  days.forEach((d, i) => {
    const hi = Math.round((inflow[i]/mx)*H), ho = Math.round((outflow[i]/mx)*H);
    const col = el('div','chart-col');
    col.innerHTML = `
      <div class="chart-bars" style="height:${H}px">
        <div class="bar bar-in"  style="height:${hi}px" title="$${inflow[i]}M"></div>
        <div class="bar bar-out" style="height:${ho}px" title="$${outflow[i]}M"></div>
      </div>
      <div class="chart-label">${d}</div>`;
    wrap.appendChild(col);
  });
}

// ── Forecast (accepts target selector) ────────────────────────────────────
export function renderForecast(forecast, selector) {
  const tbody = qs(selector); if (!tbody) return;
  tbody.innerHTML = '';
  const today = new Date();
  forecast.forEach(row => {
    const d = new Date(today); d.setDate(d.getDate() + row.daysAhead);
    const ds  = d.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'});
    const cls = row.ok ? 'ok-text' : 'risk-text';
    const lbl = row.ok ? '✓ Покрыто' : '⚠ Риск';
    const tr = el('tr');
    tr.innerHTML = `
      <td class="td-mono">${ds}</td>
      <td class="td-mono">${row.obligations}</td>
      <td class="td-mono">${row.incoming}</td>
      <td class="td-muted">${row.channel}</td>
      <td class="${cls}">${lbl}</td>`;
    tbody.appendChild(tr);
  });
}

// ── Delays ────────────────────────────────────────────────────────────────
export function renderDelays(delays) {
  const tbody = qs('#delays-tbody'); tbody.innerHTML = '';
  delays.forEach(r => {
    const tr = el('tr');
    tr.innerHTML = `<td>${r.system}</td><td class="td-mono">${r.delay}</td><td class="td-muted">${r.notes}</td>`;
    tbody.appendChild(tr);
  });
}

// ── Scenario result ────────────────────────────────────────────────────────
export function renderScenarioResult(sc) {
  const box = qs('#sc-result');
  if (!sc) { box.innerHTML = '<span class="muted-text">Выберите сценарий.</span>'; return; }
  const colorMap = { danger:'var(--risk)', warning:'var(--warn)', info:'var(--info)', ok:'var(--ok)' };
  box.innerHTML = `
    <div class="sc-label" style="color:${colorMap[sc.severity]}">${sc.label}</div>
    ${sc.lines.map(l=>`<div class="sc-line">— ${l}</div>`).join('')}`;
}

// ── Opt steps ──────────────────────────────────────────────────────────────
// ── Optimization plan (rich, from backend) ────────────────────────────────────
export function renderOptPlan(plan) {
  const wrap = qs('#opt-steps');
  wrap.innerHTML = '';

  // Summary bar
  const sumBar = el('div', 'opt-summary-bar');
  sumBar.innerHTML = `
    <span class="opt-sum-item"><span class="opt-sum-label">Действий</span><span class="opt-sum-val">${plan.instructions.length}</span></span>
    <span class="opt-sum-item"><span class="opt-sum-label">Перемещается</span><span class="opt-sum-val">${plan.totalMoved || plan.total_moved}M</span></span>
    <span class="opt-sum-item ok-text"><span class="opt-sum-label">Высвобождается</span><span class="opt-sum-val">${plan.capitalFreed || plan.capital_freed}M</span></span>
    <span class="opt-sum-item"><span class="opt-sum-label">Стоимость</span><span class="opt-sum-val">~$${Math.round((plan.totalCostUsd||plan.total_cost_usd||0)*1000)}</span></span>`;
  wrap.appendChild(sumBar);

  // Divider
  const div = el('div','opt-divider'); wrap.appendChild(div);

  // Instructions
  (plan.instructions || []).forEach(inst => {
    const urgClass = inst.urgency === 'critical' ? 'opt-row-critical' : inst.urgency === 'high' ? 'opt-row-high' : '';
    const typeIcon = inst.type === 'transfer' ? '→' : '↑';
    const chanBadge = inst.channel ? `<span class="opt-channel">${inst.channel}</span>` : '';
    const lagText   = inst.lagDays > 0 || inst.lag_days > 0 ? `<span class="opt-lag">${inst.lagDays||inst.lag_days}д</span>` : '';
    const row = el('div', `opt-step ${urgClass}`);
    row.innerHTML = `
      <span class="opt-type-icon">${typeIcon}</span>
      <span class="opt-from">${inst.label}</span>
      <div class="opt-meta-row">${chanBadge}${lagText}</div>
      <span class="opt-amount">${inst.amount}M ${inst.currency||''}</span>`;
    row.title = inst.rationale || '';
    wrap.appendChild(row);
  });
}

// ── Optimization steps (legacy fallback) ──────────────────────────────────────
export function renderOptSteps(opt) {
  const wrap = qs('#opt-steps'); wrap.innerHTML = '';
  (opt.steps||[]).forEach(s => {
    const row = el('div','opt-step');
    row.innerHTML = `
      <span class="opt-from">${s.from || s.from_}</span>
      <span class="opt-arrow">→</span>
      <span class="opt-to">${s.to}</span>
      <span class="opt-amount">${s.amount}</span>`;
    wrap.appendChild(row);
  });
}

// ── Log line ───────────────────────────────────────────────────────────────
export function appendLogLine(text, done = false) {
  const log = qs('#opt-log');
  const line = el('div', `log-line${done?' done':''}`);
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

// ── Account detail ─────────────────────────────────────────────────────────
export function renderAccountDetail(acc) {
  qs('#dm-title').textContent = `${acc.currency} / ${acc.bank}`;
  const badge = qs('#dm-status');
  badge.className = `detail-badge ${statusClass(acc.status)}`;
  badge.textContent = statusLabel(acc.status);
  const rows = [
    ['Остаток',     `${acc.balance}${acc.balanceUnit} ${acc.currency}`],
    ['Мин. резерв', `${acc.minReserve}M ${acc.currency}`],
    ['Уровень',     `${acc.fillPct}%`],
    ['Входящие',    acc.incoming],
    ['Исходящие',   acc.outgoing],
    ['Примечание',  acc.note],
  ];
  qs('#dm-rows').innerHTML = rows.map(([k,v])=>
    `<div class="detail-row"><span class="dr-key">${k}</span><span class="dr-val">${v}</span></div>`
  ).join('');
}

// ── Alert detail ───────────────────────────────────────────────────────────
export function renderAlertDetail(alert) {
  qs('#am-title').textContent = alert.title;
  const badge = qs('#am-status');
  badge.className = `detail-badge ${sevClass(alert.severity)}`;
  badge.textContent = sevLabel(alert.severity);
  qs('#am-rows').innerHTML = alert.details.map(([k,v])=>
    `<div class="detail-row"><span class="dr-key">${k}</span><span class="dr-val">${v}</span></div>`
  ).join('');
}
