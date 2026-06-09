const state = {
  data: null,
  activeRunIndex: 0,
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 4 });
};

const classForNumber = (value) => Number(value) >= 0 ? 'positive' : 'negative';
const textValue = (value) => value === null || value === undefined ? '-' : String(value);

function currentRun() {
  const runs = state.data?.runs || [];
  return runs[state.activeRunIndex] || runs[state.data?.latest_run_index || 0] || state.data?.latest || {};
}

function uniqueDates(run) {
  const source = (run.factor_leaders || []).length ? run.factor_leaders : (run.holdings || []);
  return [...new Set(source.map((row) => row.date).filter(Boolean))].sort().reverse();
}

function selectedDate() {
  return document.querySelector('#date-select').value;
}

function selectedWindow() {
  return document.querySelector('#window-select').value;
}

function recomputeWeights(rows, topN, maxWeight) {
  const selected = rows.slice(0, topN);
  if (!selected.length) return [];
  const base = Math.min(1 / selected.length, maxWeight);
  return selected.map((row, index) => ({ ...row, display_weight: base, display_rank: index + 1 }));
}

function setText(selector, value) {
  document.querySelector(selector).textContent = textValue(value);
}

function appendCell(tr, value, options = {}) {
  const td = document.createElement('td');
  if (options.className) td.className = options.className;
  if (options.badge) {
    const span = document.createElement('span');
    span.className = 'badge';
    span.textContent = textValue(value);
    td.appendChild(span);
  } else if (options.strong) {
    const strong = document.createElement('strong');
    strong.textContent = textValue(value);
    td.appendChild(strong);
  } else {
    td.textContent = textValue(value);
  }
  tr.appendChild(td);
}

function fillControls() {
  const runSelect = document.querySelector('#run-select');
  runSelect.replaceChildren();
  (state.data.runs || []).forEach((run, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${run.summary?.data_as_of || 'unknown'} · ${run.summary?.selected_factor || '-'}`;
    runSelect.appendChild(option);
  });
  runSelect.value = String(state.activeRunIndex);

  const run = currentRun();
  const windows = run.periods || [];
  const windowSelect = document.querySelector('#window-select');
  windowSelect.replaceChildren();
  windows.forEach((period) => {
    const option = document.createElement('option');
    option.value = period.key;
    option.textContent = period.label;
    windowSelect.appendChild(option);
  });
  windowSelect.value = windows[1]?.key || windows[0]?.key || '1M';

  const dates = uniqueDates(run);
  const dateSelect = document.querySelector('#date-select');
  dateSelect.replaceChildren();
  dates.forEach((date) => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = date;
    dateSelect.appendChild(option);
  });
  if (dates.length) dateSelect.value = dates[0];

  document.querySelector('#topn-input').value = run.summary?.default_top_n || 20;
  document.querySelector('#max-weight-input').value = Math.round((run.summary?.default_max_weight || 0.1) * 100);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const row = (run.factor_leaders || []).find((item) => item.date === date && item.window === windowKey);
  const summary = run.summary || {};
  setText('#best-factor', row?.best_factor || '-');
  setText('#best-factor-detail', row ? `${row.window_label} 수익률 ${formatPercent(row.best_return)}` : '-');
  setText('#selected-factor', summary.selected_factor || '-');
  setText('#selected-factor-detail', row ? `선택 팩터 순위 ${row.selected_factor_rank || '-'} · ${formatPercent(row.selected_factor_return)}` : '-');
  setText('#recommendation-status', summary.recommendation_status || '-');
  setText('#data-provider', `${summary.data_as_of || '-'} · ${summary.provider || '-'}`);

  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  const strong = document.createElement('strong');
  strong.textContent = summary.data_as_of || '-';
  statusCard.append(strong, document.createElement('br'), textValue(summary.provider || '-'), document.createElement('br'), textValue(summary.recommendation_output_label || ''));

  setText('#generated-at', `대시보드 생성: ${state.data.generated_at_utc || '-'}`);
}

function renderFactorTable() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, row.best_factor);
    appendCell(tr, formatPercent(row.best_return), { className: classForNumber(row.best_return) });
    appendCell(tr, formatPercent(row.selected_factor_return), { className: classForNumber(row.selected_factor_return) });
    appendCell(tr, row.selected_factor_rank || '-');
    tbody.appendChild(tr);
  });
}

function renderHoldingsTable() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const maxWeight = Math.max(0.01, Math.min(1, Number(document.querySelector('#max-weight-input').value || 10) / 100));
  const rows = (run.holdings || []).filter((row) => row.date === date && row.window === windowKey);
  const weighted = recomputeWeights(rows, topN, maxWeight);
  const total = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  setText('#weight-summary', `${formatPercent(total)} / 현금 ${formatPercent(Math.max(0, 1 - total))}`);
  const tbody = document.querySelector('#holdings-table tbody');
  tbody.replaceChildren();
  weighted.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.display_rank);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.display_weight));
    appendCell(tr, row.factor);
    appendCell(tr, row.score_date || row.date);
    tbody.appendChild(tr);
  });
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const rows = (run.factor_period_rankings || []).filter((row) => row.date === date).slice(0, 40);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.window_label);
    appendCell(tr, row.factor);
    appendCell(tr, formatPercent(row.period_return), { className: classForNumber(row.period_return) });
    appendCell(tr, row.rank);
    tbody.appendChild(tr);
  });
}

function renderAll() {
  renderSummary();
  renderFactorTable();
  renderHoldingsTable();
  renderPeriodRankingTable();
}

fetch('data/dashboard.json')
  .then((response) => response.json())
  .then((payload) => {
    if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.runs)) {
      throw new Error('지원하지 않는 대시보드 데이터 형식입니다.');
    }
    state.data = payload;
    state.activeRunIndex = Number.isInteger(payload.latest_run_index) ? payload.latest_run_index : Math.max(0, payload.runs.length - 1);
    fillControls();
    renderAll();
    document.querySelector('#run-select').addEventListener('change', (event) => {
      state.activeRunIndex = Number(event.target.value || 0);
      fillControls();
      renderAll();
    });
    ['#date-select', '#window-select', '#topn-input', '#max-weight-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', renderAll);
      document.querySelector(selector).addEventListener('change', renderAll);
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
