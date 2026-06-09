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

function appendEmpty(selector, message) {
  const target = document.querySelector(selector);
  target.replaceChildren();
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = message;
  target.appendChild(empty);
}

function barWidth(value, maxAbs) {
  if (!Number.isFinite(Number(value)) || maxAbs <= 0) return '0%';
  return `${Math.max(3, Math.min(100, Math.abs(Number(value)) / maxAbs * 100)).toFixed(1)}%`;
}

function currentWeightedHoldings() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const maxWeight = Math.max(0.01, Math.min(1, Number(document.querySelector('#max-weight-input').value || 10) / 100));
  const rows = (run.holdings || []).filter((row) => row.date === date && row.window === windowKey);
  const weighted = recomputeWeights(rows, topN, maxWeight);
  const total = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  return { weighted, total, topN, maxWeight };
}

function appendBarRow(target, label, valueLabel, value, maxAbs) {
  const row = document.createElement('div');
  row.className = 'bar-row';

  const labelNode = document.createElement('div');
  labelNode.className = 'bar-label';
  labelNode.textContent = textValue(label);

  const track = document.createElement('div');
  track.className = 'bar-track';
  const fill = document.createElement('div');
  fill.className = `bar-fill ${Number(value) < 0 ? 'negative' : ''}`;
  fill.style.setProperty('--bar-width', barWidth(value, maxAbs));
  track.appendChild(fill);

  const valueNode = document.createElement('div');
  valueNode.className = `bar-value ${classForNumber(value)}`;
  valueNode.textContent = valueLabel;

  row.append(labelNode, track, valueNode);
  target.appendChild(row);
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
  const { weighted, total } = currentWeightedHoldings();
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

function renderFactorReturnChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const rows = (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .slice(0, 10);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText('#factor-chart-meta', `${date || '-'} · ${windowLabel}`);
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(target, `${row.rank}. ${row.factor}`, formatPercent(row.period_return), row.period_return, maxAbs));
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const periodOrder = (run.periods || []).map((period) => period.key);
  const rows = (run.factor_leaders || [])
    .filter((row) => row.date === date)
    .sort((a, b) => periodOrder.indexOf(a.window) - periodOrder.indexOf(b.window));
  const target = document.querySelector('#window-comparison-chart');
  target.replaceChildren();
  if (!rows.length) {
    appendEmpty('#window-comparison-chart', '선택한 기준일에 기간별 최고 팩터 데이터가 없습니다.');
    return;
  }
  rows.forEach((row) => {
    const chip = document.createElement('div');
    chip.className = 'window-chip';
    const label = document.createElement('span');
    label.textContent = row.window_label || row.window;
    const factor = document.createElement('strong');
    factor.textContent = row.best_factor || '-';
    const detail = document.createElement('small');
    detail.textContent = `최고 수익률 ${formatPercent(row.best_return)} · 기존 선택 팩터 순위 ${row.selected_factor_rank || '-'}`;
    chip.append(label, factor, detail);
    target.appendChild(chip);
  });
}

function renderLeaderTrendChart() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const rows = (run.factor_leaders || [])
    .filter((row) => row.window === windowKey)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .slice(-30);
  const target = document.querySelector('#leader-trend-chart');
  target.replaceChildren();
  if (!rows.length) {
    appendEmpty('#leader-trend-chart', '선택한 기간에 최근 리더 추이 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.best_return) || 0)), 0.01);
  const bars = document.createElement('div');
  bars.className = 'trend-bars';
  rows.forEach((row) => {
    const bar = document.createElement('div');
    bar.className = 'trend-bar';
    bar.title = `${row.date} · ${row.best_factor} · ${formatPercent(row.best_return)}`;
    const fill = document.createElement('div');
    fill.className = `trend-fill ${Number(row.best_return) < 0 ? 'negative' : ''}`;
    fill.style.setProperty('--bar-height', barWidth(row.best_return, maxAbs));
    const label = document.createElement('div');
    label.className = 'trend-label';
    label.textContent = String(row.date || '').slice(5);
    bar.append(fill, label);
    bars.appendChild(bar);
  });
  target.appendChild(bars);
}

function renderWeightChart() {
  const { weighted, total, topN, maxWeight } = currentWeightedHoldings();
  const target = document.querySelector('#weight-chart');
  target.replaceChildren();
  setText('#weight-chart-meta', `상위 ${topN}개 · 최대 ${formatPercent(maxWeight)}`);
  if (!weighted.length) {
    appendEmpty('#weight-chart', '선택한 기준일과 기간에 표시할 상위 종목 데이터가 없습니다.');
    return;
  }
  const maxWeightValue = Math.max(...weighted.map((row) => Number(row.display_weight) || 0), 0.01);
  weighted.slice(0, 15).forEach((row) => appendBarRow(target, row.symbol, formatPercent(row.display_weight), row.display_weight, maxWeightValue));
  const cash = Math.max(0, 1 - total);
  if (cash > 0) {
    appendBarRow(target, '현금/미투자', formatPercent(cash), cash, Math.max(maxWeightValue, cash));
  }
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
  renderFactorReturnChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
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
