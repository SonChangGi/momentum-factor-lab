const MANUAL_UPDATE_WORKFLOW_URL = 'https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml';
const MANUAL_UPDATE_COMMAND = 'gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main';

const state = {
  data: null,
  activeRunIndex: 0,
};

function bindManualUpdateControls() {
  const button = document.querySelector('#manual-update-button');
  if (button) {
    button.setAttribute('href', MANUAL_UPDATE_WORKFLOW_URL);
    button.setAttribute('target', '_blank');
    button.setAttribute('rel', 'noopener');
    if (typeof button.addEventListener === 'function') {
      button.addEventListener('click', () => {
        const status = document.querySelector('#manual-update-status');
        if (status) {
          status.textContent = '저장소 쓰기 권한이 있는 GitHub 계정으로 Run workflow를 눌러 실행 시점의 최신 제공자 데이터 재실행을 시작하세요.';
        }
      });
    }
  }

  const command = document.querySelector('#manual-update-command');
  if (command) command.textContent = MANUAL_UPDATE_COMMAND;

  const copyButton = document.querySelector('#copy-update-command');
  if (!copyButton || typeof copyButton.addEventListener !== 'function') return;
  copyButton.addEventListener('click', async () => {
    const status = document.querySelector('#manual-update-status');
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard || !window.isSecureContext) {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(MANUAL_UPDATE_COMMAND);
      if (status) status.textContent = 'CLI 실행 명령을 복사했습니다. 터미널에서 붙여넣어 수동 실행할 수 있습니다.';
    } catch (_) {
      if (status) status.textContent = `복사가 제한되었습니다. 아래 명령을 직접 복사하세요: ${MANUAL_UPDATE_COMMAND}`;
    }
  });
}

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
const joinReasonList = (value) => {
  if (Array.isArray(value)) return value.map(textValue).filter((item) => item !== '-').join(', ');
  const text = textValue(value);
  return text === '-' ? '' : text;
};

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
  return summary.recommendation_output_key === 'recommendations'
    && summary.research_only === false
    && summary.recommendation_output_available === true
    && summary.tradable_output_available === true
    && summary.current_recommendations_available === true
    && summary.tradable_recommendations_available === true
    && summary.same_run_factor_selection_blocked_for_tradable === false
    && summary.same_sample_selection_blocked_for_tradable === false;
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
    unknown: '분류 정보 없음',
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

function runPayloadGeneratedAt(run) {
  return run?.generated_at_utc || state.data?.generated_at_utc || null;
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

function selectedFactor() {
  const selector = document.querySelector('#factor-select');
  return selector?.value || currentRun().summary?.selected_factor || '';
}

function clampNumber(value, minValue, maxValue, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minValue, Math.min(maxValue, parsed));
}

function optionalNumber(value) {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampedTopN() {
  return Math.round(clampNumber(document.querySelector('#topn-input').value, 1, 50, 20));
}

function clampedMaxWeight() {
  const percent = clampNumber(document.querySelector('#max-weight-input').value, 1, 50, 10);
  const input = document.querySelector('#max-weight-input');
  if (String(input.value) !== String(percent)) input.value = String(percent);
  return percent / 100;
}

function factorOptions(run = currentRun()) {
  const options = run.factor_options || [];
  if (options.length) return options;
  const factors = [...new Set([
    run.summary?.selected_factor,
    ...(run.factor_leaders || []).map((row) => row.best_factor),
    ...(run.factor_period_rankings || []).map((row) => row.factor),
  ].filter(Boolean))].sort();
  return factors.map((factor) => ({ factor, category: 'unknown', description_ko: '팩터 설명 정보가 없습니다.' }));
}

function factorDescription(factor, run = currentRun()) {
  const option = factorOptions(run).find((item) => item.factor === factor);
  if (!option) return '팩터 설명 정보가 없습니다.';
  const category = humanFactorCategory(option.category);
  const description = option.description_ko || option.description || '설명 정보가 없습니다.';
  return `${category} · ${description}`;
}

function periodMatrixEntry(run, date, windowKey) {
  return (run.factor_period_matrix || []).find((row) => row.date === date && row.window === windowKey) || null;
}

function periodFactorStats(run, date, windowKey, factor) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    const index = matrix.factors.indexOf(factor);
    if (index >= 0) {
      return {
        factor,
        rank: index + 1,
        period_return: optionalNumber(matrix.returns?.[index]),
        factor_count: matrix.factors.length,
        window_label: matrix.window_label || windowKey,
      };
    }
    return {
      factor,
      rank: null,
      period_return: null,
      factor_count: matrix.factors.length,
      window_label: matrix.window_label || windowKey,
    };
  }
  const row = (run.factor_period_rankings || []).find((item) => (
    item.date === date && item.window === windowKey && item.factor === factor
  ));
  if (!row) return null;
  return { ...row, rank: row.rank, factor_count: row.factor_count || null };
}

function periodBestStats(run, date, windowKey) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors) && matrix.factors.length) {
    return {
      factor: matrix.factors[0],
      rank: 1,
      period_return: optionalNumber(matrix.returns?.[0]),
      factor_count: matrix.factors.length,
      window_label: matrix.window_label || windowKey,
    };
  }
  const leader = (run.factor_leaders || []).find((item) => item.date === date && item.window === windowKey);
  if (!leader) return null;
  return {
    factor: leader.best_factor,
    rank: 1,
    period_return: leader.best_return,
    factor_count: leader.factor_count,
    window_label: leader.window_label || windowKey,
  };
}

function factorScoreSnapshot(run, date, factor) {
  return (run.factor_score_snapshots || []).find((snapshot) => snapshot.date === date && snapshot.factor === factor) || null;
}

function normalizeSnapshotRows(snapshot) {
  const rows = snapshot?.rows || [];
  return rows
    .map((row) => {
      if (Array.isArray(row)) return { symbol: row[0], score: Number(row[1]) };
      return { symbol: row.symbol, score: Number(row.score) };
    })
    .filter((row) => row.symbol && Number.isFinite(row.score))
    .sort((a, b) => Number(b.score) - Number(a.score) || String(a.symbol).localeCompare(String(b.symbol)));
}

function computeScenarioAllocation(rows, topN, maxWeight) {
  const safeRows = normalizeSnapshotRows({ rows });
  const count = Math.max(1, Math.min(50, Math.round(Number(topN) || 20), safeRows.length || 1));
  const cap = Math.max(0.01, Math.min(0.5, Number(maxWeight) || 0.1));
  const selected = safeRows.slice(0, count);
  const scores = selected.map((row) => Number(row.score) || 0);
  const minScore = scores.length ? Math.min(...scores) : 0;
  const maxScore = scores.length ? Math.max(...scores) : 0;
  const scoreRange = maxScore - minScore;
  const rawScores = scoreRange > 0
    ? scores.map((score) => score - minScore + Math.max(scoreRange * 1e-6, 1e-9))
    : selected.map((_, index) => selected.length - index);
  const weights = Array(selected.length).fill(0);
  const remainingIndexes = new Set(selected.map((_, index) => index));
  let remainingBudget = 1;
  while (remainingIndexes.size && remainingBudget > 1e-12) {
    const activeRawTotal = [...remainingIndexes].reduce((sum, index) => sum + rawScores[index], 0);
    if (activeRawTotal <= 0) break;
    const cappedThisRound = [];
    for (const index of remainingIndexes) {
      const candidateWeight = remainingBudget * (rawScores[index] / activeRawTotal);
      if (candidateWeight > cap) {
        weights[index] = cap;
        cappedThisRound.push(index);
      }
    }
    if (!cappedThisRound.length) {
      for (const index of remainingIndexes) {
        weights[index] = remainingBudget * (rawScores[index] / activeRawTotal);
      }
      remainingBudget = 0;
      break;
    }
    cappedThisRound.forEach((index) => {
      remainingIndexes.delete(index);
      remainingBudget -= weights[index];
    });
  }
  const weighted = selected.map((row, index) => ({
    ...row,
    display_rank: index + 1,
    display_weight: Math.max(0, weights[index] || 0),
    scenario_weight: Math.max(0, weights[index] || 0),
  }));
  const investedTotal = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  return {
    weighted,
    investedTotal,
    displayedTotal: investedTotal,
    portfolioTotal: investedTotal,
    cashTotal: Math.max(0, 1 - investedTotal),
    unusedCandidateCount: Math.max(0, safeRows.length - weighted.length),
    weightingMethod: 'score_proportional_capped',
    topN: count,
    maxWeight: cap,
    availableCount: safeRows.length,
  };
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

function appendStatusLine(target, label, value) {
  const row = document.createElement('div');
  row.className = 'status-line';
  const labelNode = document.createElement('span');
  labelNode.className = 'status-label';
  labelNode.textContent = label;
  const valueNode = document.createElement('span');
  valueNode.className = 'status-value';
  valueNode.textContent = textValue(value);
  row.append(labelNode, valueNode);
  target.appendChild(row);
}

function appendHeader(tr, value) {
  const th = document.createElement('th');
  th.textContent = textValue(value);
  tr.appendChild(th);
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
  const factor = selectedFactor();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const snapshot = factorScoreSnapshot(run, date, factor);
  const availableDates = run.scenario_available_dates || [];
  const allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  const stats = periodFactorStats(run, date, windowKey, factor);
  return {
    ...allocation,
    snapshot,
    selectedFactor: factor || '-',
    windowLabel: stats?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
    scoreDate: snapshot?.score_date || null,
    missingReason: snapshot
      ? null
      : availableDates.length && !availableDates.includes(date)
      ? '선택한 기준일은 용량과 로딩 속도 제한 때문에 종목/비중 스냅샷 보관 범위 밖입니다.'
      : '선택한 기준일에 이 팩터의 점수 스냅샷이 없습니다.',
  };
}

function appendBarRow(target, label, valueLabel, value, maxAbs, options = {}) {
  const row = document.createElement('div');
  row.className = `bar-row ${options.className || ''}`.trim();

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

function factorAvailableDates(run, factor) {
  const byFactor = run.scenario_available_dates_by_factor || {};
  const dates = byFactor[factor] || run.scenario_available_dates || [];
  return new Set(dates);
}

function fillDateOptions(run, preferredDate = null) {
  const dates = uniqueDates(run);
  const availableDates = factorAvailableDates(run, selectedFactor());
  const dateSelect = document.querySelector('#date-select');
  dateSelect.replaceChildren();
  dates.forEach((date) => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = availableDates.has(date) ? `${date} · 종목/비중 가능` : `${date} · 팩터 수익률만`;
    dateSelect.appendChild(option);
  });
  if (dates.length) {
    dateSelect.value = preferredDate && dates.includes(preferredDate) ? preferredDate : dates[0];
  }
}

function fillControls() {
  const runSelect = document.querySelector('#run-select');
  runSelect.replaceChildren();
  const runs = state.data.runs || [];
  runs.forEach((run, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const prefix = runs.length <= 1 ? '최신 실행만 표시' : `실행 ${index + 1}`;
    option.textContent = `${prefix} · 기준일 ${run.summary?.data_as_of || '알 수 없음'} · 실행 ${formatKoreanDateTime(run.summary?.run_timestamp_utc)} · ${run.summary?.selected_factor || '-'}`;
    runSelect.appendChild(option);
  });
  runSelect.value = String(state.activeRunIndex);
  runSelect.disabled = runs.length <= 1;

  const run = currentRun();
  const previousFactor = document.querySelector('#factor-select')?.value || run.summary?.selected_factor || '';
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

  const factorSelect = document.querySelector('#factor-select');
  const previousDate = document.querySelector('#date-select')?.value || null;
  factorSelect.replaceChildren();
  const options = factorOptions(run);
  options.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.factor;
    option.textContent = item.factor === run.summary?.selected_factor
      ? `${item.factor} · 현재 실행 선택`
      : `${item.factor} · ${humanFactorCategory(item.category)}`;
    factorSelect.appendChild(option);
  });
  const factors = options.map((item) => item.factor);
  factorSelect.value = factors.includes(previousFactor)
    ? previousFactor
    : (factors.includes(run.summary?.selected_factor) ? run.summary.selected_factor : factors[0] || '');

  fillDateOptions(run, previousDate);
  document.querySelector('#topn-input').value = run.summary?.default_top_n || 20;
  document.querySelector('#max-weight-input').value = Math.round((run.summary?.default_max_weight || 0.1) * 100);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const best = periodBestStats(run, date, windowKey);
  const factor = selectedFactor();
  const selectedStats = periodFactorStats(run, date, windowKey, factor);
  const summary = run.summary || {};
  const latestRunAt = formatKoreanDateTime(summary.run_timestamp_utc);
  const runPayloadGeneratedAtText = formatKoreanDateTime(runPayloadGeneratedAt(run));
  setText('#best-factor', best?.factor || '-');
  setText('#best-factor-detail', best ? `${best.window_label} 수익률 ${formatPercent(best.period_return)}` : '-');
  setText('#selected-factor', factor || '-');
  setText(
    '#selected-factor-detail',
    selectedStats && selectedStats.rank
      ? `${selectedStats.window_label} 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'} · ${formatPercent(selectedStats.period_return)} · ${factorDescription(factor, run)}`
      : `자료 없음 · ${factorDescription(factor, run)}`,
  );
  setText('#recommendation-status', humanStatus(summary.recommendation_status, summary.recommendation_output_label));
  setText('#data-provider', `기준일 ${summary.data_as_of || '-'} · ${humanProvider(summary.provider)}`);
  setText('#latest-run-at', latestRunAt);
  setText('#latest-run-detail', `분석 실행 기준 · 실행 결과 생성 ${runPayloadGeneratedAtText}`);

  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  statusCard.removeAttribute('aria-busy');
  statusCard.classList.remove('is-updating');
  appendStatusLine(statusCard, '데이터 기준일', summary.data_as_of || '-');
  appendStatusLine(statusCard, '최근 실행', latestRunAt);
  appendStatusLine(statusCard, '실행 결과 생성', runPayloadGeneratedAtText);
  appendStatusLine(statusCard, '데이터 제공자', humanProvider(summary.provider));
  appendStatusLine(statusCard, '신호 상태', humanOutputLabel(summary.recommendation_output_label));

  setText('#generated-at', `사이트 빌드 시각: ${formatKoreanDateTime(state.data.generated_at_utc)}`);
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
  appendDefinition(dataSummary, '최근 실행 시각', formatKoreanDateTime(summary.run_timestamp_utc));
  appendDefinition(dataSummary, '실행 결과 생성 시각', formatKoreanDateTime(runPayloadGeneratedAt(run)));
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
  const factor = selectedFactor();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const selectedStats = periodFactorStats(run, row.date, row.window, factor);
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, row.best_factor);
    appendCell(tr, formatPercent(row.best_return), { className: classForNumber(row.best_return) });
    appendCell(tr, selectedStats?.period_return == null ? '자료 없음' : formatPercent(selectedStats.period_return), { className: classForNumber(selectedStats?.period_return) });
    appendCell(tr, selectedStats?.rank ? `${selectedStats.rank}/${selectedStats.factor_count || '-'}` : '자료 없음');
    tbody.appendChild(tr);
  });
}

function renderHoldingsTable() {
  const run = currentRun();
  const {
    weighted,
    displayedTotal,
    portfolioTotal,
    cashTotal,
    topN,
    availableCount,
    selectedFactor: factor,
    windowLabel,
    scoreDate,
    unusedCandidateCount,
    maxWeight,
    missingReason,
  } = currentWeightedHoldings();
  const weightLabel = isPracticalRun(run) ? '표시용 투자 시나리오 비중' : '표시용 연구 시나리오 비중';
  setText(
    '#weight-summary',
    `시나리오 배분 ${formatPercent(portfolioTotal)} · 화면 표시 ${formatPercent(displayedTotal)} · 현금/미사용 ${formatPercent(cashTotal)}`,
  );
  const capNote = topN * maxWeight < 1
    ? `종목 수와 최대 비중 가정상 ${formatPercent(cashTotal)}는 현금/미사용으로 남습니다.`
    : '선택한 종목 수와 최대 비중 가정으로 100% 배분이 가능합니다.';
  setText(
    '#holdings-availability',
    missingReason
      ? `${missingReason} 기간 최고 팩터 보유를 대신 보여주지 않습니다.`
      : run.history_payload_type === 'summary'
      ? '이전 실행은 페이지 속도를 위해 요약 이력만 보관합니다. 상위 종목과 비중은 최신 실행에서 전체 표시됩니다.'
      : `${windowLabel} 선택 팩터 ${factor}의 ${scoreDate || '최근'} 점수 스냅샷 기준입니다. 전체 ${formatInteger(availableCount)}개 후보 중 상위 ${Math.min(topN, availableCount)}개를 표시하며, ${weightLabel}은 브라우저가 팩터 점수 비례 배분과 종목당 최대 ${formatPercent(maxWeight)} 가정으로 계산합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`,
  );
  const tbody = document.querySelector('#holdings-table tbody');
  tbody.replaceChildren();
  if (!weighted.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.textContent = '선택한 기준일과 팩터에 표시할 점수 스냅샷이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  weighted.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.display_rank);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.display_weight));
    appendCell(tr, factor);
    appendCell(tr, scoreDate || selectedDate());
    tbody.appendChild(tr);
  });
}

function renderCurrentOutputTable() {
  const run = currentRun();
  const summary = run.summary || {};
  const quality = run.data_quality_summary || {};
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const rows = (run.latest_output_rows || []).slice(0, topN);
  const tbody = document.querySelector('#current-output-table tbody');
  const note = document.querySelector('#current-output-note');
  tbody.replaceChildren();
  if (note) {
    const isResearch = !isPracticalRun(run);
    const blockers = joinReasonList(summary.tradability_blockers) || joinReasonList(summary.fail_closed_reasons) || '실전 매매 게이트 미통과';
    const candidateCount = formatCount(summary.candidate_universe_size ?? quality.candidate_universe_size);
    const eligibleCount = formatCount(summary.eligible_price_universe_size ?? quality.eligible_price_universe_size);
    const liquidityCount = formatCount(summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size);
    note.textContent = isResearch
      ? `연구용 fail-closed 출력입니다. 최종 매매 비중과 목표금액은 0으로 고정하고, 게이트 전 모형 비중만 후보 간 상대 강도 진단으로 표시합니다. 미충족 요건: ${blockers}. 후보 ${candidateCount}, 가격 적격 ${eligibleCount}, 유동성 적격 ${liquidityCount}.`
      : `실행 가능성 게이트를 통과한 최신 추천입니다. 후보 ${candidateCount}, 가격 적격 ${eligibleCount}, 유동성 적격 ${liquidityCount}.`;
  }
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
  const factor = selectedFactor();
  const best = periodBestStats(run, date, windowKey);
  const matrix = periodMatrixEntry(run, date, windowKey);
  let rows = [];
  if (matrix && Array.isArray(matrix.factors)) {
    rows = matrix.factors.map((name, index) => ({
      factor: name,
      rank: index + 1,
      period_return: optionalNumber(matrix.returns?.[index]),
      window_label: matrix.window_label,
    }));
  } else {
    rows = (run.factor_period_rankings || []).filter((row) => row.date === date && row.window === windowKey);
  }
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 10);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText('#factor-chart-meta', `${date || '-'} · ${windowLabel} · 선택 ${factor || '-'}`);
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(
    target,
    `${row.rank}. ${row.factor}`,
    formatPercent(row.period_return),
    row.period_return,
    maxAbs,
    { className: `${row.factor === factor ? 'is-selected' : ''} ${row.factor === best?.factor ? 'is-best' : ''}`.trim() },
  ));
  if (!selectedRow) {
    const note = document.createElement('div');
    note.className = 'scenario-note';
    note.textContent = '선택 팩터가 이 기준일/기간의 내보낸 순위 데이터에 없습니다. 팩터 비교는 가능한 데이터 범위 안에서만 표시됩니다.';
    target.appendChild(note);
  }
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const selectedFactorName = selectedFactor();
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
    const factorNode = document.createElement('strong');
    factorNode.textContent = row.best_factor || '-';
    const detail = document.createElement('small');
    const selectedStats = periodFactorStats(run, row.date, row.window, selectedFactorName);
    detail.textContent = selectedStats?.rank
      ? `최고 수익률 ${formatPercent(row.best_return)} · 선택 팩터 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'}`
      : `최고 수익률 ${formatPercent(row.best_return)} · 선택 팩터 자료 없음`;
    chip.append(label, factorNode, detail);
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
  const { weighted, cashTotal, topN, maxWeight, unusedCandidateCount } = currentWeightedHoldings();
  const target = document.querySelector('#weight-chart');
  target.replaceChildren();
  setText('#weight-chart-meta', `${isPracticalRun(run) ? '투자 시나리오' : '연구 시나리오'} · 상위 ${topN}개 · 브라우저 최대 ${formatPercent(maxWeight)}`);
  if (!weighted.length) {
    appendEmpty('#weight-chart', '선택한 기준일과 팩터에 표시할 상위 종목 점수 스냅샷이 없습니다.');
    return;
  }
  const maxWeightValue = Math.max(
    ...weighted.map((row) => Number(row.display_weight) || 0),
    Number(cashTotal) || 0,
    0.01,
  );
  weighted.forEach((row) => appendBarRow(target, row.symbol, formatPercent(row.display_weight), row.display_weight, maxWeightValue));
  if (cashTotal > 0.000001) {
    appendBarRow(target, '현금/미사용', formatPercent(cashTotal), cashTotal, maxWeightValue);
  }
  if (unusedCandidateCount > 0) {
    const note = document.createElement('div');
    note.className = 'scenario-note';
    note.textContent = `상위 N개 제한 때문에 ${formatInteger(unusedCandidateCount)}개 후보는 이번 브라우저 시나리오 목표 비중에서 제외했습니다.`;
    target.appendChild(note);
  }
}

function factorBacktestSeries(run, factor) {
  return (run.factor_backtest_series || []).find((series) => series.factor === factor) || null;
}

function benchmarkBacktestSeries(run) {
  const series = run.benchmark_backtest_series;
  if (!series || !Array.isArray(series.dates)) return null;
  return series;
}

function seriesPointsThroughDate(series, date, limit = 260) {
  if (!series || !Array.isArray(series.dates)) return [];
  const points = series.dates.map((pointDate, index) => ({
    date: pointDate,
    equity: Number(series.equity?.[index]),
    drawdown: Number(series.drawdown?.[index]),
  })).filter((point) => point.date && Number.isFinite(point.equity));
  const through = date ? points.filter((point) => String(point.date) <= String(date)) : points;
  return through.slice(-limit);
}

function normalizedLine(points) {
  if (!points.length) return [];
  const base = points[0].equity || 1;
  return points.map((point) => ({ ...point, normalized: base ? point.equity / base : point.equity }));
}

function formatAxisDate(value) {
  if (!value) return '-';
  const parts = String(value).split('-');
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
  return String(value);
}

function formatChartAxisDate(value, mode = 'month') {
  if (!value) return '-';
  const parts = String(value).split('-').map((part) => Number(part));
  if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return formatAxisDate(value);
  const [year, month, day] = parts;
  if (mode === 'quarter') return `${String(year).slice(2)}년 ${Math.floor((month - 1) / 3) + 1}분기`;
  if (mode === 'week') return `${month}/${day}`;
  return `${String(year).slice(2)}.${String(month).padStart(2, '0')}`;
}

function parseDateString(value) {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function daysBetween(start, end) {
  const startDate = parseDateString(start);
  const endDate = parseDateString(end);
  if (!startDate || !endDate) return 0;
  return Math.max(0, Math.round((endDate - startDate) / 86400000));
}

function dateTickKey(year, month, day, mode) {
  if (mode === 'week') return `${year}-${String(month).padStart(2, '0')}-W${Math.ceil(day / 7)}`;
  if (mode === 'quarter') return `${year}-Q${Math.floor((month - 1) / 3) + 1}`;
  return `${year}-${String(month).padStart(2, '0')}`;
}

function dateTickMarks(dates) {
  if (!dates.length) return [];
  const spanDays = daysBetween(dates[0], dates.at(-1));
  const mode = spanDays <= 70 ? 'week' : (spanDays <= 420 ? 'month' : 'quarter');
  const ticks = [];
  let previousKey = '';
  dates.forEach((date, index) => {
    const parts = String(date).split('-').map((part) => Number(part));
    if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return;
    const [year, month, day] = parts;
    const key = dateTickKey(year, month, day, mode);
    if (index === 0 || index === dates.length - 1 || key !== previousKey) {
      if (mode !== 'quarter' || index === 0 || index === dates.length - 1 || [1, 4, 7, 10].includes(month)) {
        ticks.push({ index, date, label: formatChartAxisDate(date, mode) });
      }
    }
    previousKey = key;
  });
  const maxTicks = 12;
  if (ticks.length <= maxTicks) return ticks;
  const stride = Math.ceil((ticks.length - 2) / (maxTicks - 2));
  return ticks.filter((tick, index) => index === 0 || index === ticks.length - 1 || index % stride === 0);
}

function formatPercentTick(value) {
  if (!Number.isFinite(Number(value))) return '-';
  const percent = Number(value) * 100;
  const decimals = Math.abs(percent) < 10 && Math.abs(percent % 1) > 0.001 ? 1 : 0;
  return `${percent.toFixed(decimals)}%`;
}

function niceReturnTicks(minReturn, maxReturn) {
  let lower = Math.min(Number(minReturn) || 0, 0);
  let upper = Math.max(Number(maxReturn) || 0, 0);
  if (Math.abs(upper - lower) < 0.02) {
    lower -= 0.02;
    upper += 0.02;
  }
  const candidates = [0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0, 5.0];
  let step = candidates.at(-1);
  for (const candidate of candidates) {
    const start = Math.floor(lower / candidate) * candidate;
    const end = Math.ceil(upper / candidate) * candidate;
    const count = Math.round((end - start) / candidate) + 1;
    if (count >= 4 && count <= 7) {
      step = candidate;
      break;
    }
  }
  const start = Math.floor(lower / step) * step;
  const end = Math.ceil(upper / step) * step;
  const ticks = [];
  for (let value = start; value <= end + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

const PERFORMANCE_PERIODS = [
  { key: '1W', label: '최근 1주', tradingDays: 5 },
  { key: '1M', label: '최근 1개월', tradingDays: 21 },
  { key: '3M', label: '최근 3개월', tradingDays: 63 },
  { key: '6M', label: '최근 6개월', tradingDays: 126 },
  { key: '1Y', label: '최근 1년', tradingDays: 252 },
  { key: 'YTD', label: 'YTD', ytd: true },
];

const PERFORMANCE_METRICS = [
  { key: 'cumulativeReturn', label: '누적 수익률', formatter: formatPercent },
  { key: 'sharpe', label: '샤프지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'volatility', label: '변동성(표준편차)', formatter: formatPercent },
  { key: 'maxDrawdown', label: 'MDD', formatter: formatPercent },
  { key: 'sortino', label: '소르티노 지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'calmar', label: '칼마 지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'cvar', label: 'CVaR(95%)', formatter: formatPercent },
  { key: 'winRate', label: '일간 승률', formatter: formatPercent },
];

function formatNumberWithDigits(value, digits = 2) {
  if (value === Infinity) return '∞';
  if (value === -Infinity) return '-∞';
  if (value === null || value === undefined || Number.isNaN(Number(value)) || !Number.isFinite(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function periodPoints(points, period) {
  if (!points.length) return [];
  if (period.ytd) {
    const endYear = String(points.at(-1).date || '').slice(0, 4);
    const ytdPoints = points.filter((point) => String(point.date || '').startsWith(endYear));
    return ytdPoints.length >= 2 ? ytdPoints : points.slice(-Math.min(points.length, 2));
  }
  return points.slice(-Math.min(points.length, period.tradingDays + 1));
}

function returnSeries(points) {
  const returns = [];
  for (let index = 1; index < points.length; index += 1) {
    const previous = Number(points[index - 1].equity);
    const current = Number(points[index].equity);
    if (Number.isFinite(previous) && Number.isFinite(current) && previous > 0) {
      returns.push(current / previous - 1);
    }
  }
  return returns;
}

function populationStd(values) {
  if (values.length < 2) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(Math.max(0, variance));
}

function maxDrawdownFromPoints(points) {
  let peak = -Infinity;
  let maxDrawdown = 0;
  points.forEach((point) => {
    const equity = Number(point.equity);
    if (!Number.isFinite(equity)) return;
    peak = Math.max(peak, equity);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, equity / peak - 1);
  });
  return maxDrawdown;
}

function cvarFromReturns(returns, tail = 0.05) {
  const clean = returns.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!clean.length) return null;
  const count = Math.max(1, Math.ceil(clean.length * tail));
  const tailReturns = clean.slice(0, count);
  return tailReturns.reduce((sum, value) => sum + value, 0) / tailReturns.length;
}

function performanceMetrics(points, period) {
  const slice = periodPoints(points, period);
  if (slice.length < 2) return null;
  const returns = returnSeries(slice);
  if (!returns.length) return null;
  const first = Number(slice[0].equity);
  const last = Number(slice.at(-1).equity);
  const cumulativeReturn = first > 0 ? last / first - 1 : null;
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const std = populationStd(returns);
  const downside = returns.filter((value) => value < 0);
  const downsideStd = downside.length >= 2 ? populationStd(downside) : null;
  const annualizedReturn = cumulativeReturn === null || cumulativeReturn <= -1
    ? null
    : ((1 + cumulativeReturn) ** (252 / returns.length) - 1);
  const volatility = std === null ? null : std * Math.sqrt(252);
  const maxDrawdown = maxDrawdownFromPoints(slice);
  const winRate = returns.filter((value) => value > 0).length / returns.length;
  return {
    cumulativeReturn,
    sharpe: std && std > 0 ? (mean / std) * Math.sqrt(252) : null,
    volatility,
    maxDrawdown,
    sortino: downside.length === 0 && mean > 0 ? Infinity : (downsideStd && downsideStd > 0 ? (mean / downsideStd) * Math.sqrt(252) : null),
    calmar: maxDrawdown < 0 && annualizedReturn !== null ? annualizedReturn / Math.abs(maxDrawdown) : null,
    cvar: cvarFromReturns(returns),
    winRate,
  };
}

function appendSvgText(svg, text, x, y, className, anchor = 'middle') {
  const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  label.textContent = text;
  label.setAttribute('x', String(x));
  label.setAttribute('y', String(y));
  label.setAttribute('class', className);
  label.setAttribute('text-anchor', anchor);
  svg.appendChild(label);
  return label;
}

function renderBacktestChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const best = periodBestStats(run, date, windowKey);
  const benchmark = benchmarkBacktestSeries(run);
  const selectedSeries = normalizedLine(seriesPointsThroughDate(factorBacktestSeries(run, factor), date));
  const bestMetricSeries = best?.factor
    ? normalizedLine(seriesPointsThroughDate(factorBacktestSeries(run, best.factor), date))
    : [];
  const bestSeries = best?.factor && best.factor !== factor ? bestMetricSeries : [];
  const benchmarkSeries = normalizedLine(seriesPointsThroughDate(benchmark, date));
  const benchmarkLabel = benchmark?.label_ko || benchmark?.symbol || run.summary?.chart_benchmark || '나스닥 벤치마크';
  const target = document.querySelector('#backtest-chart');
  target.replaceChildren();
  setText(
    '#backtest-chart-meta',
    `${date || '-'} 기준 · 선택 ${factor || '-'}${best?.factor ? ` · 기간 최고 ${best.factor}` : ''}${benchmarkSeries.length ? ` · 벤치마크 ${benchmarkLabel}` : ''}`
  );
  if (!selectedSeries.length) {
    appendEmpty('#backtest-chart', '선택 팩터의 최근 백테스트 추이 데이터가 없습니다. 기간 최고 팩터 데이터를 대신 표시하지 않습니다.');
    renderPerformanceMetricsTable([]);
    return;
  }
  const allPoints = [...selectedSeries, ...bestSeries, ...benchmarkSeries];
  const allValues = allPoints.map((point) => point.normalized).filter((value) => Number.isFinite(value));
  const returnValues = allValues.map((value) => value - 1);
  const tickReturns = niceReturnTicks(Math.min(...returnValues, 0), Math.max(...returnValues, 0));
  const minValue = Math.min(...tickReturns) + 1;
  const maxValue = Math.max(...tickReturns) + 1;
  const allDates = [...new Set(allPoints.map((point) => point.date).filter(Boolean))].sort();
  const dateToIndex = new Map(allDates.map((pointDate, index) => [pointDate, index]));
  const width = 760;
  const height = 260;
  const plot = { left: 68, right: 18, top: 18, bottom: 50 };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '선택 팩터, 기간 최고 팩터, 나스닥 벤치마크의 최근 백테스트 누적 성과 비교');
  const yFor = (value) => height - plot.bottom - ((value - minValue) / Math.max(0.000001, maxValue - minValue)) * plotHeight;
  const xFor = (point) => {
    const index = dateToIndex.get(point.date) ?? 0;
    return plot.left + (allDates.length <= 1 ? 0 : index / (allDates.length - 1) * plotWidth);
  };
  tickReturns.forEach((tickReturn) => {
    const y = yFor(tickReturn + 1);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', String(plot.left));
    line.setAttribute('x2', String(width - plot.right));
    line.setAttribute('y1', String(y));
    line.setAttribute('y2', String(y));
    line.setAttribute('class', 'line-grid');
    svg.appendChild(line);
    appendSvgText(svg, formatPercentTick(tickReturn), plot.left - 9, y + 4, 'axis-label', 'end');
  });
  const yAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  yAxis.setAttribute('x1', String(plot.left));
  yAxis.setAttribute('x2', String(plot.left));
  yAxis.setAttribute('y1', String(plot.top));
  yAxis.setAttribute('y2', String(height - plot.bottom));
  yAxis.setAttribute('class', 'axis-line');
  svg.appendChild(yAxis);
  const xAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  xAxis.setAttribute('x1', String(plot.left));
  xAxis.setAttribute('x2', String(width - plot.right));
  xAxis.setAttribute('y1', String(height - plot.bottom));
  xAxis.setAttribute('y2', String(height - plot.bottom));
  xAxis.setAttribute('class', 'axis-line');
  svg.appendChild(xAxis);
  dateTickMarks(allDates).forEach((tickMark) => {
    const { index } = tickMark;
    const x = plot.left + (allDates.length <= 1 ? 0 : index / (allDates.length - 1) * plotWidth);
    const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    tick.setAttribute('x1', String(x));
    tick.setAttribute('x2', String(x));
    tick.setAttribute('y1', String(height - plot.bottom));
    tick.setAttribute('y2', String(height - plot.bottom + 5));
    tick.setAttribute('class', 'axis-line');
    svg.appendChild(tick);
    appendSvgText(svg, tickMark.label, x, height - plot.bottom + 19, 'axis-label');
  });
  appendSvgText(svg, 'X축: 날짜', plot.left + plotWidth / 2, height - 5, 'axis-title');
  const yTitle = appendSvgText(svg, 'Y축: 누적 성과', 13, plot.top + plotHeight / 2, 'axis-title');
  yTitle.setAttribute('transform', `rotate(-90 13 ${plot.top + plotHeight / 2})`);
  const toPolyline = (points) => points.map((point) => {
    const x = xFor(point);
    const y = yFor(point.normalized);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const appendLine = (points, className) => {
    if (!points.length) return;
    const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    polyline.setAttribute('points', toPolyline(points));
    polyline.setAttribute('class', `line-path ${className}`);
    svg.appendChild(polyline);
  };
  appendLine(selectedSeries, 'selected');
  appendLine(bestSeries, 'best');
  appendLine(benchmarkSeries, 'benchmark');
  target.appendChild(svg);

  const legend = document.createElement('div');
  legend.className = 'line-legend';
  const selectedReturn = selectedSeries.at(-1)?.normalized - 1;
  const bestReturn = bestSeries.length ? bestSeries.at(-1)?.normalized - 1 : null;
  const benchmarkReturn = benchmarkSeries.length ? benchmarkSeries.at(-1)?.normalized - 1 : null;
  const selectedDrawdown = selectedSeries.at(-1)?.drawdown;
  const bestDrawdown = bestSeries.length ? bestSeries.at(-1)?.drawdown : null;
  const benchmarkDrawdown = benchmarkSeries.length ? benchmarkSeries.at(-1)?.drawdown : null;
  const selectedLegend = document.createElement('span');
  const selectedDot = document.createElement('span');
  selectedDot.className = 'legend-dot';
  selectedLegend.appendChild(selectedDot);
  selectedLegend.append(`선택 팩터 ${factor}: 구간 ${formatPercent(selectedReturn)} · 낙폭 ${formatPercent(selectedDrawdown)}`);
  legend.appendChild(selectedLegend);
  if (bestSeries.length) {
    const bestLegend = document.createElement('span');
    const bestDot = document.createElement('span');
    bestDot.className = 'legend-dot best';
    bestLegend.appendChild(bestDot);
    bestLegend.append(`기간 최고 ${best.factor}: 구간 ${formatPercent(bestReturn)} · 낙폭 ${formatPercent(bestDrawdown)}`);
    legend.appendChild(bestLegend);
  }
  if (benchmarkSeries.length) {
    const benchmarkLegend = document.createElement('span');
    const benchmarkDot = document.createElement('span');
    benchmarkDot.className = 'legend-dot benchmark';
    benchmarkLegend.appendChild(benchmarkDot);
    benchmarkLegend.append(`${benchmarkLabel}: 구간 ${formatPercent(benchmarkReturn)} · 낙폭 ${formatPercent(benchmarkDrawdown)}`);
    legend.appendChild(benchmarkLegend);
  }
  target.appendChild(legend);
  renderPerformanceMetricsTable([
    { key: 'selected', label: `선택 팩터 ${factor || '-'}`, points: selectedSeries },
    {
      key: 'best',
      label: `기간 최고 팩터 ${best?.factor || '-'}`,
      points: bestMetricSeries.length ? bestMetricSeries : selectedSeries,
    },
    { key: 'benchmark', label: benchmarkLabel, points: benchmarkSeries },
  ]);
}

function renderPerformanceMetricsTable(seriesList) {
  const target = document.querySelector('#performance-metrics-table');
  if (!target) return;
  target.replaceChildren();
  const availableSeries = (seriesList || []).filter((series) => Array.isArray(series.points) && series.points.length >= 2);
  if (!availableSeries.length) {
    appendEmpty('#performance-metrics-table', '성과 지표를 계산할 수 있는 누적 성과 데이터가 없습니다.');
    return;
  }

  const heading = document.createElement('div');
  heading.className = 'performance-metrics-heading';
  const headingText = document.createElement('div');
  const title = document.createElement('h4');
  title.textContent = '기간별 성과 지표 비교';
  const note = document.createElement('p');
  note.textContent = '각 기간 카드에서 같은 지표의 선택 팩터·기간 최고 팩터·나스닥 값을 한 줄로 비교합니다. 샤프·변동성·소르티노·칼마는 백엔드와 동일하게 일간 수익률 population 표준편차(ddof=0)로 연율화하며, CVaR은 최악 5% 일간 손실 평균입니다. 1주·1개월 지표는 표본이 짧아 참고용입니다.';
  headingText.append(title, note);
  heading.appendChild(headingText);
  target.appendChild(heading);

  const metricCache = new Map(availableSeries.map((series) => [
    series.key,
    new Map(PERFORMANCE_PERIODS.map((period) => [period.key, performanceMetrics(series.points, period)])),
  ]));
  const shortSeriesLabel = (series) => ({
    selected: '선택 팩터',
    best: '기간 최고',
    benchmark: '나스닥',
  })[series.key] || series.label;

  const grid = document.createElement('div');
  grid.className = 'performance-period-grid';
  PERFORMANCE_PERIODS.forEach((period) => {
    const card = document.createElement('section');
    card.className = 'performance-period-card';
    const periodTitle = document.createElement('h5');
    periodTitle.textContent = period.label;
    card.appendChild(periodTitle);

    const wrap = document.createElement('div');
    wrap.className = 'performance-table-wrap';
    const table = document.createElement('table');
    table.className = 'performance-table';
    table.setAttribute('aria-label', `${period.label} 선택 팩터, 기간 최고 팩터, 나스닥 벤치마크 성과 지표 비교`);
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    appendHeader(header, '지표');
    availableSeries.forEach((series) => {
      const th = document.createElement('th');
      const label = document.createElement('span');
      label.className = `series-name ${series.key}`;
      label.textContent = shortSeriesLabel(series);
      th.appendChild(label);
      header.appendChild(th);
    });
    thead.appendChild(header);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    PERFORMANCE_METRICS.forEach((metric) => {
      const tr = document.createElement('tr');
      appendCell(tr, metric.label, { strong: true });
      availableSeries.forEach((series) => {
        const metrics = metricCache.get(series.key)?.get(period.key);
        const value = metrics?.[metric.key];
        const signedMetric = ['cumulativeReturn', 'maxDrawdown', 'cvar'].includes(metric.key);
        const className = signedMetric && Number.isFinite(Number(value)) ? classForNumber(value) : '';
        appendCell(tr, metric.formatter(value), { className });
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);
    grid.appendChild(card);
  });
  target.appendChild(grid);
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const matrix = periodMatrixEntry(run, date, windowKey);
  let rows = [];
  if (matrix && Array.isArray(matrix.factors)) {
    rows = matrix.factors.map((name, index) => ({
      window_label: matrix.window_label || windowKey,
      factor: name,
      period_return: optionalNumber(matrix.returns?.[index]),
      rank: index + 1,
    }));
  } else {
    rows = (run.factor_period_rankings || []).filter((row) => row.date === date && row.window === windowKey);
  }
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 40);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.window_label);
    appendCell(tr, row.factor, { strong: row.factor === factor });
    appendCell(tr, formatPercent(row.period_return), { className: classForNumber(row.period_return) });
    appendCell(tr, row.rank);
    tbody.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 4;
    td.textContent = '선택한 기준일과 기간에 팩터 랭킹 자료가 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

function renderAll() {
  renderSummary();
  renderDiagnostics();
  renderFactorReturnChart();
  renderBacktestChart();
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

bindManualUpdateControls();

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
    document.querySelector('#factor-select').addEventListener('change', () => {
      fillDateOptions(currentRun(), selectedDate());
      renderWithBusy('선택 팩터를 반영하는 중입니다...');
    });
    ['#date-select', '#window-select', '#topn-input', '#max-weight-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => renderWithBusy('선택값을 반영하는 중입니다...'));
      document.querySelector(selector).addEventListener('change', () => renderWithBusy('선택값을 반영하는 중입니다...'));
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
