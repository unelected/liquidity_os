// search.js — Client-side search & offline-capable features
// Works entirely without network: filtering, search, export.

import { state } from './app.js';
import { renderAccounts, renderAlerts } from './ui.js';

// ── Universal search ───────────────────────────────────────────────────────────
export function initSearch() {
  const input = document.querySelector('#search-input');
  if (!input) return;
  input.addEventListener('input', () => runSearch(input.value.trim()));
  document.querySelector('#search-clear')?.addEventListener('click', () => {
    input.value = '';
    runSearch('');
  });
}

export function runSearch(query) {
  const q = query.toLowerCase();
  const clearBtn = document.querySelector('#search-clear');
  if (clearBtn) clearBtn.style.display = q ? 'flex' : 'none';

  const resultsWrap = document.querySelector('#search-results');
  if (!resultsWrap) return;

  if (!q) { resultsWrap.style.display = 'none'; return; }

  const results = [];

  // Search accounts
  (state.data?.accounts || []).forEach(acc => {
    const text = `${acc.currency} ${acc.bank} ${acc.balance} ${acc.note}`.toLowerCase();
    if (text.includes(q)) {
      results.push({
        type: 'account',
        title: `${acc.currency} / ${acc.bank}`,
        sub: `Остаток ${acc.balance}M · ${acc.note}`,
        action: () => window.App.openAccountModal(acc.id),
      });
    }
  });

  // Search alerts
  (state.data?.alerts || []).forEach(alert => {
    const text = `${alert.title} ${alert.description} ${alert.meta || ''}`.toLowerCase();
    if (text.includes(q)) {
      results.push({
        type: 'alert',
        title: alert.title,
        sub: alert.description.slice(0, 80) + '…',
        action: () => window.App.openAlertModal(alert.id),
      });
    }
  });

  // Search scenarios
  const scenarios = state.data?.stressScenarios || {};
  Object.entries(scenarios).forEach(([key, sc]) => {
    if (sc.label.toLowerCase().includes(q) || sc.lines.join(' ').toLowerCase().includes(q)) {
      results.push({
        type: 'scenario',
        title: `Сценарий: ${sc.label}`,
        sub: sc.lines[0],
        action: () => { window.App.showTab('forecast'); window.App.runScenario(key); },
      });
    }
  });

  resultsWrap.innerHTML = '';
  if (!results.length) {
    resultsWrap.innerHTML = '<div class="sr-empty">Ничего не найдено</div>';
  } else {
    results.forEach(r => {
      const typeLabel = { account: 'Счёт', alert: 'Алерт', scenario: 'Сценарий' }[r.type];
      const div = document.createElement('div');
      div.className = 'sr-item';
      div.innerHTML = `
        <span class="sr-type">${typeLabel}</span>
        <div class="sr-body">
          <div class="sr-title">${r.title}</div>
          <div class="sr-sub">${r.sub}</div>
        </div>`;
      div.addEventListener('click', () => {
        r.action();
        resultsWrap.style.display = 'none';
        document.querySelector('#search-input').value = '';
        document.querySelector('#search-clear').style.display = 'none';
      });
      resultsWrap.appendChild(div);
    });
  }
  resultsWrap.style.display = 'block';

  // Close on outside click
  const close = (e) => {
    if (!resultsWrap.contains(e.target) && e.target.id !== 'search-input') {
      resultsWrap.style.display = 'none';
      document.removeEventListener('click', close);
    }
  };
  setTimeout(() => document.addEventListener('click', close), 0);
}

// ── Account filter (dashboard table) ──────────────────────────────────────────
export function initAccountFilter() {
  const sel = document.querySelector('#account-filter');
  if (!sel) return;
  sel.addEventListener('change', () => filterAccounts(sel.value));
}

export function filterAccounts(status) {
  const all = state.data?.accounts || [];
  const filtered = status === 'all' ? all : all.filter(a => a.status === status);
  renderAccounts(filtered);
  attachAccountRowListeners();
}

// ── Alert filter ───────────────────────────────────────────────────────────────
export function initAlertFilter() {
  document.querySelectorAll('.alert-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.alert-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterAlerts(btn.dataset.filter);
    });
  });
}

export function filterAlerts(sev) {
  const all = state.data?.alerts || [];
  const filtered = sev === 'all' ? all : all.filter(a => a.severity === sev);
  renderAlerts(filtered);
  attachAlertRowListeners();
}

// ── CSV export (client-side, no server needed) ─────────────────────────────────
export function exportAccountsCSV() {
  const accounts = state.data?.accounts;
  if (!accounts) return;

  const header = ['Валюта','Банк','Остаток','Уровень %','Статус','Примечание'];
  const rows = accounts.map(a =>
    [a.currency, a.bank, `${a.balance}M`, a.fillPct, a.status, a.note]
      .map(v => `"${v}"`).join(',')
  );
  const csv = [header.join(','), ...rows].join('\n');

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `accounts_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Row listener helpers (called after re-renders) ─────────────────────────────
export function attachAccountRowListeners() {
  document.querySelectorAll('.account-row').forEach(row => {
    row.addEventListener('click', () => window.App.openAccountModal(row.dataset.id));
  });
}

export function attachAlertRowListeners() {
  document.querySelectorAll('.alert-row').forEach(row => {
    row.addEventListener('click', () => window.App.openAlertModal(row.dataset.id));
  });
}
