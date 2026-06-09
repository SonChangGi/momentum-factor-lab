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

const formatInteger = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0 });
};

const formatCount = (value) => {
  const formatted = formatInteger(value);
  return formatted === '-' ? '-' : `${formatted}개`;
};

const classForNumber = (value) => Number(value) >= 0 ? 'positive' : 'negative';
const textValue = (value) => value === null || value === undefined ? '-' : String(value);

function formatKoreanDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return textValue(value);
  return `${date.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })} KST`;
}

function humanProvider(value) {
  const text = textValue(value);
  const labels = {
    'yfinance-free-public-data': '야후 파이낸스 무료 공개 데이터',
    'stooq-fallback': 'Stooq 무료 일별 종가 대체 데이터',
    'finance-datareader-fallback': 'FinanceDataReader 무료 종가 대체 데이터',
    'no-live-price-provider': '사용 가능한 실시간 가격 제공자 없음',
    'offline-sample': '오프라인 샘플 데이터',
    'offline_sample': '오프라인 샘플 데이터',
  };
  if (text.includes('+')) {
    return text.split('+').map((part) => labels[part] || `기타 제공자(${part})`).join(' + ');
  }
  return labels[text] || text;
}

function humanOutputLabel(value) {
  const text = textValue(value);
  const labels = {
    'Research signals (not tradable)': '연구용 신호(매매 권고 아님)',
    'Practical recommendations': '실행 가능성 검토를 통과한 추천 후보',
    'No current recommendation': '현재 추천 후보 없음',
  };
  return labels[text] || text;
}

function humanStatus(status, outputLabel) {
  const text = textValue(status);
  if (text === '-') return humanOutputLabel(outputLabel);
  if (text === 'sample_offline_not_current') {
    return '오프라인 샘플 · 현재 추천 아님';
  }
  if (text === 'current_live') {
    return '최신 데이터 · 실행 가능성 점검 통과';
  }
  if (text.includes('subset')) {
    return '일부 종목 실행 · 연구용 신호';
  }
  if (text.includes('with_limitations')) {
    return '최신 데이터 · 제한 조건 때문에 연구용 신호';
  }
  if (text.includes('research') || String(outputLabel || '').includes('Research signals')) {
    return '현재 데이터 사용 · 연구용 신호 · 매매 권고 아님';
  }
  if (text.includes('pass')) {
    return '현재 데이터 사용 · 품질 점검 통과';
  }
  if (text.includes('stale')) {
    return '데이터가 최신이 아닐 수 있음';
  }
  if (text.includes('fail') || text.includes('blocked')) {
    return '제한 조건 때문에 추천 보류';
  }
  return text;
}

function isPracticalRun(run = currentRun()) {
  const summary = run.summary || {};
  return String(summary.recommendation_output_label || '').includes('Practical')
    || String(summary.recommendation_status || '') === 'current_live';
}

function humanFactorCategory(value) {
  const text = textValue(value);
  const labels = {
    traditional: '전통 모멘텀',
    recent: '최근 수익률',
    composite: '복합 모멘텀',
    risk_adjusted: '위험조정 모멘텀',
    trend: '추세/이동평균',
    drawdown: '낙폭/고점 근접',
    breakout: '돌파',
    reversal: '반전 보정',
    acceleration: '가속도',
    quality: '추세 품질',
    cross_sectional: '횡단면 상대강도',
    robust: '이상치 완화',
    range: '가격 범위 위치',
  };
  return labels[text] || `기타(${text})`;
}

function humanWeightingMethod(value) {
  const text = textValue(value);
  const labels = {
    equal: '동일 비중',
    score_size_liquidity: '점수·규모·유동성 기반',
  };
  return labels[text] || text;
}

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

function setText(selector, value) {
  document.querySelector(selector).textContent = textValue(value);
}

function appendDefinition(target, label, value) {
  const dt = document.createElement('dt');
  dt.textContent = label;
  const dd = document.createElement('dd');
  dd.textContent = textValue(value);
  target.append(dt, dd);
}

function formatCounts(counts, labels = {}) {
  if (!counts || typeof counts !== 'object' || Array.isArray(counts)) return '-';
  const entries = Object.entries(counts).filter(([, value]) => Number(value) > 0);
  if (!entries.length) return '-';
  return entries
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([key, value]) => `${labels[key] || key} ${formatInteger(value)}`)
    .join(' · ');
}

function setStatusMessage(message) {
  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  statusCard.textContent = message;
  statusCard.setAttribute('aria-busy', 'true');
  statusCard.classList.add('is-updating');
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
  const allRows = (run.holdings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .map((row) => ({ ...row, actual_weight: Number(row.default_weight || 0) }));
  const weighted = allRows
    .slice(0, topN)
    .map((row, index) => ({
      ...row,
      display_weight: row.actual_weight,
      display_rank: index + 1,
    }));
  const displayedTotal = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  const portfolioTotal = allRows.reduce((sum, row) => sum + row.actual_weight, 0);
  const unshownTotal = Math.max(0, portfolioTotal - displayedTotal);
  const cashTotal = Math.max(0, 1 - portfolioTotal);
  return {
    weighted,
    displayedTotal,
    portfolioTotal,
    unshownTotal,
    cashTotal,
    topN,
    maxWeight,
    availableCount: allRows.length,
    selectedFactor: allRows[0]?.factor || '-',
    windowLabel: allRows[0]?.window_label || windowKey || '-',
  };
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
  const runs = state.data.runs || [];
  runs.forEach((run, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const prefix = runs.length <= 1 ? '최신 실행만 표시' : `실행 ${index + 1}`;
    option.textContent = `${prefix} · ${run.summary?.data_as_of || '알 수 없음'} · ${run.summary?.selected_factor || '-'}`;
    runSelect.appendChild(option);
  });
  runSelect.value = String(state.activeRunIndex);
  runSelect.disabled = runs.length <= 1;

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
  setText('#recommendation-status', humanStatus(summary.recommendation_status, summary.recommendation_output_label));
  setText('#data-provider', `${summary.data_as_of || '-'} · ${humanProvider(summary.provider)}`);

  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  statusCard.removeAttribute('aria-busy');
  statusCard.classList.remove('is-updating');
  const strong = document.createElement('strong');
  strong.textContent = summary.data_as_of || '-';
  statusCard.append(
    strong,
    document.createElement('br'),
    textValue(humanProvider(summary.provider)),
    document.createElement('br'),
    textValue(humanOutputLabel(summary.recommendation_output_label)),
  );

  setText('#generated-at', `대시보드 생성 시각: ${formatKoreanDateTime(state.data.generated_at_utc)}`);
}

function renderDiagnostics() {
  const run = currentRun();
  const summary = run.summary || {};
  const quality = run.data_quality_summary || {};
  const dataSummary = document.querySelector('#data-quality-summary');
  dataSummary.replaceChildren();
  appendDefinition(dataSummary, '후보 종목', formatCount(summary.candidate_universe_size ?? quality.candidate_universe_size));
  appendDefinition(dataSummary, '가격 적격 종목', formatCount(summary.eligible_price_universe_size ?? quality.eligible_price_universe_size));
  appendDefinition(dataSummary, '유동성 적격 종목', formatCount(summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size));
  appendDefinition(dataSummary, '가격 수집 종목', formatCount(quality.fetched_price_symbol_count));
  appendDefinition(dataSummary, '제외 종목 수', formatCount(quality.excluded_symbols));
  appendDefinition(dataSummary, '데이터 기준일', quality.data_as_of || summary.data_as_of || '-');
  appendDefinition(dataSummary, '가격 제공자', humanProvider(quality.provider || summary.provider));
  appendDefinition(
    dataSummary,
    '품질 상태',
    formatCounts(quality.data_quality_status_counts, {
      pass: '통과',
      missing_price: '가격 누락',
      missing_volume: '거래량 누락',
      provider_adjustment_incompatible: '조정가격 불일치',
      stale_price: '오래된 가격',
      insufficient_history: '이력 부족',
      below_liquidity_floor: '유동성 부족',
      benchmark_comparator_only: '벤치마크 전용',
    }),
  );
  appendDefinition(dataSummary, '유동성 상태', formatCounts(quality.liquidity_status_counts, { pass: '통과', fail: '미통과' }));
  appendDefinition(dataSummary, '용량 상태', formatCounts(quality.capacity_status_counts, { pass: '통과', fail: '미통과' }));

  const gateTarget = document.querySelector('#tradability-gate-list');
  gateTarget.replaceChildren();
  const gates = run.tradability_gate || [];
  if (!gates.length) {
    appendEmpty('#tradability-gate-list', '추천/신호 게이트 정보가 없습니다.');
  } else {
    gates.forEach((gate) => {
      const item = document.createElement('div');
      item.className = `gate-item ${gate.passed ? 'pass' : 'block'}`;
      const title = document.createElement('strong');
      title.textContent = `${gate.passed ? '통과' : '점검 필요'} · ${gate.label_ko || gate.key}`;
      const detail = document.createElement('small');
      detail.textContent = gate.description_ko || '추가 실행 가능성 점검 항목입니다.';
      item.append(title, detail);
      gateTarget.appendChild(item);
    });
  }

  const diagnostics = run.factor_diagnostics || {};
  setText('#factor-scope-note', diagnostics.scope_note_ko || '팩터 진단 정보가 없습니다.');

  const categoryTarget = document.querySelector('#factor-category-summary');
  categoryTarget.replaceChildren();
  const categories = diagnostics.category_summary || [];
  if (!categories.length) {
    appendEmpty('#factor-category-summary', '팩터 카테고리 요약이 없습니다.');
  } else {
    categories.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = `${humanFactorCategory(row.category)} · ${formatInteger(row.factor_count)}개`;
      const detail = document.createElement('small');
      detail.textContent = `평균 Rank-IC ${formatNumber(row.avg_mean_rank_ic)} · 양수 비율 ${formatPercent(row.avg_positive_ic_rate)} · 예: ${row.example_factors || '-'}`;
      item.append(title, detail);
      categoryTarget.appendChild(item);
    });
  }

  const icTarget = document.querySelector('#factor-rank-ic-summary');
  icTarget.replaceChildren();
  const rankIcRows = diagnostics.rank_ic_top || [];
  if (!rankIcRows.length) {
    appendEmpty('#factor-rank-ic-summary', 'Forward Rank-IC 진단이 없습니다.');
  } else {
    rankIcRows.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = row.factor || '-';
      const detail = document.createElement('small');
      detail.textContent = `${formatInteger(row.horizon_days ?? diagnostics.rank_ic_horizon_days)}거래일 후 Rank-IC ${formatNumber(row.mean_rank_ic)} · 관측 ${formatInteger(row.observations)}회 · 양수 비율 ${formatPercent(row.positive_ic_rate)} · 중첩 일별 관측`;
      item.append(title, detail);
      icTarget.appendChild(item);
    });
  }

  const redundancyTarget = document.querySelector('#factor-redundancy-summary');
  redundancyTarget.replaceChildren();
  const redundancyRows = diagnostics.redundancy_top || [];
  if (!redundancyRows.length) {
    appendEmpty('#factor-redundancy-summary', '팩터 중복도 진단이 없습니다.');
  } else {
    redundancyRows.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = `${row.factor || '-'} ↔ ${row.nearest_factor || '-'}`;
      const detail = document.createElement('small');
      detail.textContent = `순위상관 ${formatNumber(row.signed_rank_corr)} · 높은 상관 피어 ${formatInteger(row.high_corr_peer_count)}개 · 진단일 ${row.diagnostic_date || '-'}`;
      item.append(title, detail);
      redundancyTarget.appendChild(item);
    });
  }
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
  const { weighted, displayedTotal, portfolioTotal, unshownTotal, cashTotal, topN, availableCount, selectedFactor, windowLabel } = currentWeightedHoldings();
  const weightLabel = isPracticalRun(run) ? '투자 비중' : '모형/연구 비중';
  setText(
    '#weight-summary',
    `전체 ${formatPercent(portfolioTotal)} · 표시 ${formatPercent(displayedTotal)} · 미표시 ${formatPercent(unshownTotal)} · 현금 ${formatPercent(cashTotal)}`,
  );
  setText(
    '#holdings-availability',
    run.history_payload_type === 'summary'
      ? '이전 실행은 페이지 속도를 위해 요약 이력만 보관합니다. 상위 종목과 비중은 최신 실행에서 전체 표시됩니다.'
      : `${windowLabel} 최고 팩터 ${selectedFactor} 기준 백테스트 보유입니다. 전체 ${formatInteger(availableCount)}개 중 상위 ${Math.min(topN, availableCount)}개를 표시하며, ${weightLabel}은 기존 분석 코드가 저장한 일별 보유 비중을 그대로 사용합니다.`,
  );
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

function renderCurrentOutputTable() {
  const run = currentRun();
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const rows = (run.latest_output_rows || []).slice(0, topN);
  const tbody = document.querySelector('#current-output-table tbody');
  tbody.replaceChildren();
  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.rank || index + 1);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.weight), { className: classForNumber(row.weight) });
    appendCell(tr, formatPercent(row.pre_cap_weight), { className: classForNumber(row.pre_cap_weight) });
    appendCell(tr, humanWeightingMethod(row.weighting_method));
    appendCell(tr, row.signal_date || run.summary?.data_as_of || '-');
    tbody.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 7;
    td.textContent = '최신 추천/연구 신호 출력 행이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
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
  const run = currentRun();
  const { weighted, unshownTotal, cashTotal, topN, maxWeight } = currentWeightedHoldings();
  const target = document.querySelector('#weight-chart');
  target.replaceChildren();
  setText('#weight-chart-meta', `${isPracticalRun(run) ? '투자 비중' : '모형/연구 비중'} · 상위 ${topN}개 표시 · 실행 목표 최대 ${formatPercent(maxWeight)}`);
  if (!weighted.length) {
    appendEmpty('#weight-chart', '선택한 기준일과 기간에 표시할 상위 종목 데이터가 없습니다.');
    return;
  }
  const maxWeightValue = Math.max(
    ...weighted.map((row) => Number(row.display_weight) || 0),
    Number(unshownTotal) || 0,
    Number(cashTotal) || 0,
    0.01,
  );
  weighted.forEach((row) => appendBarRow(target, row.symbol, formatPercent(row.display_weight), row.display_weight, maxWeightValue));
  if (unshownTotal > 0.000001) {
    appendBarRow(target, '미표시 보유분', formatPercent(unshownTotal), unshownTotal, maxWeightValue);
  }
  if (cashTotal > 0.000001) {
    appendBarRow(target, '현금/미투자', formatPercent(cashTotal), cashTotal, maxWeightValue);
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
  renderDiagnostics();
  renderFactorReturnChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
  renderCurrentOutputTable();
  renderFactorTable();
  renderHoldingsTable();
  renderPeriodRankingTable();
}

function renderWithBusy(message = '선택값을 반영하는 중입니다...') {
  setStatusMessage(message);
  window.setTimeout(() => {
    renderAll();
  }, 160);
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
      renderWithBusy('실행 결과를 전환하는 중입니다...');
    });
    ['#date-select', '#window-select', '#topn-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => renderWithBusy('선택값을 반영하는 중입니다...'));
      document.querySelector(selector).addEventListener('change', () => renderWithBusy('선택값을 반영하는 중입니다...'));
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
