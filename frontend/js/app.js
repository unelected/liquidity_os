// app.js — Main orchestrator

import { loadData, postOptimize, computeDynamicAlerts } from './data.js';
import {
  renderOfflineBanner, renderSummary, renderAccounts, renderAlerts,
  renderDashboardAlerts, renderChart, renderForecast, renderDelays,
  renderOptSteps, renderOptPlan, appendLogLine, renderAccountDetail, renderAlertDetail,
  renderScenarioResult, qs,
} from './ui.js';
import {
  initSearch, initAccountFilter, initAlertFilter,
  attachAccountRowListeners, attachAlertRowListeners,
  filterAccounts, filterAlerts, exportAccountsCSV,
} from './search.js';

export const state = {
  data: null, offline: false,
  activeTab: 'dashboard', optimized: false,
};

// ── Boot ───────────────────────────────────────────────────────────────────
async function boot() {
  const { data, offline } = await loadData();
  state.data    = data;
  state.offline = offline;

  renderOfflineBanner(offline);
  // Offline: backend won't compute dynamic alerts — run them client-side
  if (offline) {
    const dynamic = computeDynamicAlerts(data);
    const skipIds = new Set(['alert-anomaly-txn','alert-distribution','alert-excess-reserves']);
    const base = data.alerts.filter(a => !skipIds.has(a.id) && !a.id.startsWith('alert-clearing-'));
    const order = {danger:0,warning:1,info:2,ok:3};
    data.alerts = [...base,...dynamic].sort((a,b)=>(order[a.severity]??9)-(order[b.severity]??9));
    state.data = data;
  }
  renderAll(data);
  initSearch();
  initAccountFilter();
  initAlertFilter();
  attachAccountRowListeners();
  attachAlertRowListeners();
  attachModalListeners();
}

function renderAll(data) {
  renderSummary(data.summary);
  renderAccounts(data.accounts);
  renderAlerts(data.alerts);
  renderDashboardAlerts(data.alerts);
  renderChart(data.cashflow, '#cashflow-chart');
  renderChart(data.cashflow, '#cashflow-chart-2');
  renderForecast(data.forecast, '#forecast-tbody');
  renderForecast(data.forecast, '#forecast-tbody-2');
  renderDelays(data.clearingDelays);
}

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(id) {
  state.activeTab = id;
  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('active', p.id === 'page-' + id));
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === id));
}

// ── Scenario ───────────────────────────────────────────────────────────────
function runScenario(key) {
  document.querySelectorAll('.sc-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.sc === key));
  renderScenarioResult(state.data?.stressScenarios?.[key]);
}

// ── Account modal ──────────────────────────────────────────────────────────
function openAccountModal(id) {
  const acc = state.data?.accounts?.find(a => a.id === id);
  if (!acc) return;
  renderAccountDetail(acc);
  openModal('account-modal');
}

// ── Alert modal ────────────────────────────────────────────────────────────
function openAlertModal(id) {
  const alert = state.data?.alerts?.find(a => a.id === id);
  if (!alert) return;
  renderAlertDetail(alert);
  openModal('alert-modal');
}

// ── Optimization modal ─────────────────────────────────────────────────────
function openOptModal() {
  if (!state.data?.optimization) return;
  // Show loading state first
  qs('#opt-steps').innerHTML = '<div class="opt-loading">Загрузка плана…</div>';
  qs('#opt-steps').style.display   = 'flex';
  qs('#opt-log').innerHTML = '';
  qs('#opt-log').classList.remove('show');
  qs('#opt-actions').style.display = 'flex';
  openModal('opt-modal');

  // Try to load live plan from backend, fallback to seed data
  fetch(`${window._API_BASE || 'http://localhost:8000/api'}/optimize/plan`, {
    signal: AbortSignal.timeout(4000),
  })
    .then(r => r.ok ? r.json() : null)
    .catch(() => null)
    .then(plan => {
      if (plan?.instructions?.length) {
        renderOptPlan(plan);
      } else {
        renderOptSteps(state.data.optimization);
      }
    });
}

async function confirmOptimization() {
  qs('#opt-actions').style.display = 'none';
  qs('#opt-steps').style.display   = 'none';
  qs('#opt-log').classList.add('show');

  const offline = state.offline;
  const pfx = offline ? '[офлайн] ' : '';
  const steps = [
    [300,  'Анализ текущих балансов…'],
    [800,  'Расчёт оптимального распределения…'],
    [1400, pfx + 'USD/JPM → EUR/Barclays $1.3M'],
    [2000, pfx + 'AED/Emirates → GBP/HSBC $0.4M'],
    [2600, 'Высвобождение резервов CHF $0.8M'],
    [3200, '✓ Оптимизация применена' + (offline ? ' (симуляция)' : '')],
  ];
  steps.forEach(([delay, text]) => {
    setTimeout(() => {
      appendLogLine(text, text.startsWith('✓'));
      if (text.startsWith('✓')) {
        setTimeout(() => { applyOptResult(); closeModal('opt-modal'); }, 700);
      }
    }, delay);
  });
  if (!offline) await postOptimize();
}

function applyOptResult() {
  state.optimized = true;
  const impact = state.data.optimization.impact;
  state.data.summary.frozenReserves.value   = impact.frozenAfter;
  state.data.summary.gapRisk.level          = impact.riskAfter;
  state.data.summary.gapRisk.label          = impact.riskAfterLabel;
  state.data.summary.gapRisk.accountsAtRisk = 0;
  const eur = state.data.accounts.find(a => a.id === 'eur');
  if (eur) { eur.status = 'ok'; eur.balance = 1.9; eur.fillPct = 64; }
  const ea  = state.data.alerts.find(a => a.id === 'alert-eur');
  if (ea) {
    ea.severity    = 'ok';
    ea.title       = 'EUR / Barclays — разрыв устранён';
    ea.description = 'Перевод $1.3M из USD/JPMorgan выполнен. Остаток €1.9M покрывает обязательства.';
    ea.meta        = 'Оптимизация применена';
  }
  renderSummary(state.data.summary);
  renderAccounts(state.data.accounts);
  renderAlerts(state.data.alerts);
  renderDashboardAlerts(state.data.alerts);
  attachAccountRowListeners();
  attachAlertRowListeners();
}

// ── Retry ──────────────────────────────────────────────────────────────────
async function retryConnection() {
  const { data, offline } = await loadData();
  state.data = data; state.offline = offline;
  renderOfflineBanner(offline);
  if (!offline) renderAll(data);
}

// ── Modal helpers ──────────────────────────────────────────────────────────
function openModal(id)  { qs('#' + id)?.classList.add('open'); }
function closeModal(id) { qs('#' + id)?.classList.remove('open'); }

function attachModalListeners() {
  document.querySelectorAll('.modal-overlay').forEach(o => {
    o.addEventListener('click', e => { if (e.target === o) o.classList.remove('open'); });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape')
      document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  });
}

// ── Global App object ──────────────────────────────────────────────────────
window.App = {
  showTab, runScenario,
  openAccountModal, openAlertModal, openOptModal,
  confirmOptimization, closeModal, retryConnection,
  exportAccountsCSV,
  filterAccounts: (v) => { filterAccounts(v); attachAccountRowListeners(); },
  filterAlerts:   (v) => { filterAlerts(v);   attachAlertRowListeners(); },
};

boot();
