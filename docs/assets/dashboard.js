const MANUAL_UPDATE_WORKFLOW_URL = 'https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml';
const MANUAL_UPDATE_COMMAND = 'gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main';

const FACTOR_METHOD_OVERRIDES = {
  "mom_12_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-273] - 1",
    "description": "Traditional 12-1 cross-sectional total return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_9_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-210] - 1",
    "description": "Nine-month skipped return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_6_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-147] - 1",
    "description": "Traditional 6-1 cross-sectional total return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_12_2": {
    "category": "traditional",
    "formula": "P[t-42] / P[t-294] - 1",
    "description": "Twelve-month momentum with a two-month skip to reduce reversal contamination.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_3_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-84] - 1",
    "description": "Traditional 3-1 skipped return momentum.",
    "validation": "Independent shifted-return and no-lookahead tests."
  },
  "mom_10d": {
    "category": "recent",
    "formula": "P[t] / P[t-10] - 1",
    "description": "Ten-trading-day short-horizon momentum with high-turnover warning.",
    "validation": "Literal golden-vector simple-return tests and turnover warning audit."
  },
  "mom_6m_unskipped": {
    "category": "recent",
    "formula": "P[t] / P[t-126] - 1",
    "description": "Six-month recent momentum without a skip window.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_3m": {
    "category": "recent",
    "formula": "P[t] / P[t-63] - 1",
    "description": "Three-month recent momentum without skip month.",
    "validation": "Simple-return fixture tests."
  },
  "mom_2m": {
    "category": "recent",
    "formula": "P[t] / P[t-42] - 1",
    "description": "Two-month short-horizon momentum for fast leadership changes.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_2_1": {
    "category": "recent",
    "formula": "P[t-21] / P[t-63] - 1",
    "description": "Two-month momentum that skips the most recent month.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_6m": {
    "category": "recent",
    "formula": "P[t-10] / P[t-136] - 1",
    "description": "Six-month momentum ending ten trading days before the signal date to avoid very recent reversal noise.",
    "validation": "Independent shifted-return and no-lookahead tests; intentionally distinct from mom_6m_unskipped."
  },
  "mom_12m": {
    "category": "recent",
    "formula": "P[t] / P[t-252] - 1",
    "description": "Twelve-month simple momentum without skip month.",
    "validation": "Independent simple-return and no-lookahead tests."
  },
  "mom_1m": {
    "category": "recent",
    "formula": "P[t] / P[t-21] - 1",
    "description": "One-month short-horizon momentum.",
    "validation": "Simple-return fixture tests."
  },
  "multi_horizon": {
    "category": "composite",
    "formula": "0.15*1m + 0.25*3m(skip5) + 0.30*6m(skip10) + 0.30*12m(skip21)",
    "description": "Weighted 1/3/6/12-month multi-horizon momentum composite.",
    "validation": "Component helper tests plus output audit."
  },
  "vol_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / annualized_vol_63d",
    "description": "Six-month momentum scaled by recent annualized volatility.",
    "validation": "Division-by-zero and finite coverage audit."
  },
  "risk_adjusted": {
    "category": "risk_adjusted",
    "formula": "annualized_mean_return_126d / annualized_vol_126d",
    "description": "Rolling Sharpe-like annualized return divided by volatility.",
    "validation": "Rolling mean/vol helper tests."
  },
  "downside_risk_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / annualized_downside_vol_126d",
    "description": "Momentum scaled by downside volatility only.",
    "validation": "Downside fixture tests and finite audit."
  },
  "dual_momentum": {
    "category": "trend",
    "formula": "6m relative momentum penalized when price < MA200",
    "description": "Relative momentum penalized when absolute trend is below the 200-day average.",
    "validation": "Trend penalty and no-lookahead audit."
  },
  "ma_trend": {
    "category": "trend",
    "formula": "P/MA200 - 1 + 0.5*(MA50/MA200 - 1)",
    "description": "Trend persistence from price/MA200 and MA50/MA200 structure.",
    "validation": "Moving-average fixture tests."
  },
  "time_series_trend": {
    "category": "trend",
    "formula": "I(P>MA20)+I(MA20>MA100)+I(MA100>MA200)",
    "description": "Discrete time-series trend stack across short/intermediate/long averages.",
    "validation": "Bounded 0..3 output audit."
  },
  "drawdown_aware": {
    "category": "drawdown",
    "formula": "6m(skip10) + P/rolling_high_126 - 1",
    "description": "Six-month momentum penalized by recent drawdown from rolling high.",
    "validation": "Drawdown sign and no-lookahead audit."
  },
  "high_52w": {
    "category": "drawdown",
    "formula": "P / rolling_high_252 - 1",
    "description": "Closeness to 52-week high; less negative is stronger.",
    "validation": "Manual rolling-high fixture tests."
  },
  "high_26w": {
    "category": "drawdown",
    "formula": "P / rolling_high_126 - 1",
    "description": "Closeness to a 26-week high for intermediate breakout confirmation.",
    "validation": "Independent rolling-high golden tests."
  },
  "breakout_63d": {
    "category": "breakout",
    "formula": "P/rolling_high_63 - 1 + 0.5*1m",
    "description": "Recent breakout pressure with one-month confirmation.",
    "validation": "Rolling-high plus 1m fixture tests."
  },
  "breakout_126d": {
    "category": "breakout",
    "formula": "P/rolling_high_126 - 1 + 0.5*3m",
    "description": "Intermediate breakout pressure with three-month confirmation.",
    "validation": "Independent rolling-high golden tests."
  },
  "reversal_adjusted": {
    "category": "reversal",
    "formula": "12-1 momentum - 0.35*1m momentum",
    "description": "12-1 momentum adjusted for short-term reversal risk.",
    "validation": "Component helper tests plus no-lookahead audit."
  },
  "acceleration": {
    "category": "acceleration",
    "formula": "3m momentum - 0.5*6-1 momentum",
    "description": "Momentum acceleration toward recent leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "short_acceleration": {
    "category": "acceleration",
    "formula": "1m momentum - 0.5*3m momentum",
    "description": "Short-horizon acceleration signal for very recent leadership surges.",
    "validation": "Independent raw-shift golden tests."
  },
  "decay_adjusted": {
    "category": "acceleration",
    "formula": "6m(skip10) - 0.25*abs(1m momentum)",
    "description": "Six-month momentum penalized when very recent moves look overextended.",
    "validation": "Independent raw-shift golden tests."
  },
  "consistency": {
    "category": "quality",
    "formula": "6m(skip10) * rolling_positive_return_ratio_126d",
    "description": "Rewards momentum earned consistently across days.",
    "validation": "Positive-ratio fixture tests."
  },
  "persistent_12_1": {
    "category": "quality",
    "formula": "12m(skip21) * positive_daily_return_ratio_252d(skip21)",
    "description": "Long-horizon skipped momentum scaled by the share of positive daily returns in the skipped formation window.",
    "validation": "Positive-ratio and no-lookahead tests."
  },
  "low_vol_momentum": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) - annualized_vol_63d",
    "description": "Momentum penalized by high recent volatility.",
    "validation": "Low-vol ranking fixture tests."
  },
  "stability_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / (1 + annualized_vol_126d)",
    "description": "Six-month momentum damped by one-year realized volatility from price returns.",
    "validation": "Independent volatility golden tests."
  },
  "relative_strength_6m": {
    "category": "cross_sectional",
    "formula": "cross-sectional percentile_rank(6m(skip10))",
    "description": "Six-month relative-strength percentile within the eligible universe.",
    "validation": "Cross-sectional rank audit."
  },
  "trend_quality": {
    "category": "quality",
    "formula": "P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126",
    "description": "Combines trend slope with smoothness of returns.",
    "validation": "Rolling helper and finite audit."
  },
  "gap_resistant": {
    "category": "robust",
    "formula": "compound clipped daily returns over 126d",
    "description": "Momentum using clipped daily returns to reduce single-gap dominance.",
    "validation": "Clipped-return fixture tests."
  },
  "winsorized_skip": {
    "category": "robust",
    "formula": "compound clipped daily returns over 126d after 10d skip",
    "description": "Skipped six-month momentum using winsorized daily returns to reduce gap dominance.",
    "validation": "Independent clipped-return golden tests."
  },
  "price_efficiency": {
    "category": "quality",
    "formula": "6m(skip10) * |P/P[t-126]-1| / sum_126(|daily_return|)",
    "description": "Rewards six-month momentum that traveled a direct, low-chop price path.",
    "validation": "Path-efficiency fixture tests and division-by-zero audit."
  },
  "range_position": {
    "category": "range",
    "formula": "6m(skip10) + (P-low_126)/(high_126-low_126) - 0.5",
    "description": "Combines six-month momentum with where price sits inside its trailing range.",
    "validation": "Rolling-range fixture tests and flat-range audit."
  },
  "range_position_252d": {
    "category": "range",
    "formula": "12m(skip21) + (P-low_252)/(high_252-low_252) - 0.5",
    "description": "Combines long-horizon skipped momentum with position inside a 52-week range.",
    "validation": "Independent rolling-range golden tests."
  },
  "median_return_3m": {
    "category": "robust",
    "formula": "median(daily_return, 63d) * 63",
    "description": "Three-month median daily return momentum to reduce outlier sensitivity.",
    "validation": "Median-return golden-vector and outlier-gap tests."
  },
  "median_return_6m": {
    "category": "robust",
    "formula": "median(daily_return, 126d) * 126",
    "description": "Six-month median daily return momentum to reduce outlier sensitivity.",
    "validation": "Median-return golden-vector and no-lookahead tests."
  },
  "winsorized_3m": {
    "category": "robust",
    "formula": "compound clipped [-8%, +8%] daily returns over 63d",
    "description": "Three-month winsorized compounded momentum.",
    "validation": "Winsorized golden-vector and outlier-gap tests."
  },
  "winsorized_12m": {
    "category": "robust",
    "formula": "compound clipped [-8%, +8%] daily returns over 252d",
    "description": "Twelve-month winsorized compounded momentum.",
    "validation": "Winsorized no-lookahead and edge-case tests."
  },
  "vol_adjusted_3m": {
    "category": "risk_adjusted",
    "formula": "3m simple momentum / annualized_vol_63d",
    "description": "Three-month momentum scaled by recent annualized volatility.",
    "validation": "Division-by-zero and finite coverage audit."
  },
  "vol_adjusted_12m": {
    "category": "risk_adjusted",
    "formula": "12-1 momentum / annualized_vol_126d",
    "description": "Twelve-minus-one momentum scaled by intermediate volatility.",
    "validation": "Division-by-zero and no-lookahead audit."
  },
  "downside_adjusted_12m": {
    "category": "risk_adjusted",
    "formula": "12-1 momentum / annualized_downside_vol_252d",
    "description": "Twelve-minus-one momentum scaled by downside volatility.",
    "validation": "Downside risk edge-case tests."
  },
  "ma_slope_50": {
    "category": "trend",
    "formula": "MA50[t] / MA50[t-21] - 1",
    "description": "One-month slope of the 50-day moving average.",
    "validation": "Moving-average slope fixture tests."
  },
  "price_vs_ma200": {
    "category": "trend",
    "formula": "P / MA200 - 1",
    "description": "Distance of price above/below the 200-day moving average.",
    "validation": "Moving-average fixture tests."
  },
  "ma_stack_quality": {
    "category": "trend",
    "formula": "I(P>MA20)+I(MA20>MA50)+I(MA50>MA100)+I(MA100>MA200)",
    "description": "Four-step moving-average stack quality score.",
    "validation": "Bounded 0..4 output and no-lookahead audit."
  },
  "breakout_20d": {
    "category": "breakout",
    "formula": "P/rolling_high_20 - 1 + 0.5*10d",
    "description": "Short breakout proximity with ten-day confirmation.",
    "validation": "Rolling-high golden-vector tests."
  },
  "accel_1m_vs_3m": {
    "category": "acceleration",
    "formula": "1m momentum - 3m momentum",
    "description": "Acceleration from three-month to one-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "accel_3m_vs_6m": {
    "category": "acceleration",
    "formula": "3m momentum - 6m momentum",
    "description": "Acceleration from six-month to three-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "accel_6m_vs_12m": {
    "category": "acceleration",
    "formula": "6m momentum - 12m momentum",
    "description": "Acceleration from twelve-month to six-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "ulcer_adjusted": {
    "category": "drawdown",
    "formula": "6m(skip10) / sqrt(mean(drawdown_126^2, 126d))",
    "description": "Momentum scaled by Ulcer-style drawdown severity.",
    "validation": "Drawdown denominator and finite audit."
  },
  "smooth_return_6m": {
    "category": "quality",
    "formula": "6m simple momentum - rolling_std_daily_return_126d",
    "description": "Six-month return momentum penalized by daily return roughness.",
    "validation": "Smoothness edge-case tests."
  },
  "residual_12_1": {
    "category": "cross_sectional",
    "formula": "sum_252(return shifted21) - beta_252_to_equal_weight_market * sum_252(market_return shifted21)",
    "description": "Twelve-minus-one beta-neutral residual momentum versus the equal-weight candidate-universe proxy.",
    "validation": "Rolling beta residual formula, rank-distinctness, and no-lookahead tests."
  },
  "excess_ir_6m": {
    "category": "cross_sectional",
    "formula": "annualized_mean(excess_return_126d) / annualized_tracking_error_126d",
    "description": "Six-month information-ratio style momentum versus the equal-weight candidate universe.",
    "validation": "Tracking-error denominator and no-lookahead tests."
  },
  "up_down_capture_6m": {
    "category": "asymmetry",
    "formula": "mean(return | market_up,126d) - abs(mean(return | market_down,126d))",
    "description": "Rewards stocks that participate on up-market days without giving back as much on down-market days.",
    "validation": "Market-up/down conditioning and finite-coverage tests."
  },
  "tail_resilient_6m": {
    "category": "tail_risk",
    "formula": "6m(skip10) + q05(daily_return,126d)",
    "description": "Six-month skipped momentum penalized by poor left-tail daily returns.",
    "validation": "Rolling quantile edge-case and no-lookahead tests."
  },
  "jump_excluded_6m": {
    "category": "robust",
    "formula": "sum_126(daily_return shifted10) - max_126(daily_return shifted10)",
    "description": "Formation-window momentum that removes the single largest daily jump to reduce one-day gap dominance.",
    "validation": "Independent shifted-return and outlier-resistance tests."
  },
  "high_persistence_6m": {
    "category": "quality",
    "formula": "mean_63(I(P >= 0.98*rolling_high_126))",
    "description": "Fraction of recent days spent near a six-month high, capturing persistent leadership rather than one-day proximity.",
    "validation": "Rolling-high persistence and no-lookahead tests."
  }
};

const DASHBOARD_INPUT_DEFAULTS = {
  window: '1Y',
  lookbackMonths: 12,
  topN: 20,
  maxWeightPercent: 50,
  rebalanceFrequency: 'ME',
  transactionCostBps: 5,
  slippageBps: 5,
};

const state = {
  data: null,
  activeRunIndex: 0,
  hasUserSelectedFactor: false,
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
    'yahoo-chart-fallback': 'Yahoo chart 조정종가 보강 데이터',
    'nasdaq-latest-repair': 'Nasdaq 최신 종가 보강 데이터',
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
    score_proportional_capped: '팩터 점수 비례·상한 적용',
    best_factor_score_proportional_capped: '최고 팩터 점수 비례·상한 적용',
    top_factor_equal_sleeve: '상위 팩터 동일비중 합산',
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

function selectedLookbackMonths() {
  const selector = document.querySelector('#lookback-months-select');
  return Math.round(clampNumber(selector?.value, 1, 60, DASHBOARD_INPUT_DEFAULTS.lookbackMonths));
}

function selectedRebalanceFrequency() {
  const selector = document.querySelector('#rebalance-select');
  const value = selector?.value || DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
  return ['W', 'ME', 'QE'].includes(value) ? value : DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
}

function clampedTransactionCostBps() {
  const input = document.querySelector('#transaction-cost-input');
  const value = clampNumber(input?.value, 0, 200, DASHBOARD_INPUT_DEFAULTS.transactionCostBps);
  if (input && String(input.value) !== String(value)) input.value = String(value);
  return value;
}

function clampedSlippageBps() {
  const input = document.querySelector('#slippage-input');
  const value = clampNumber(input?.value, 0, 200, DASHBOARD_INPUT_DEFAULTS.slippageBps);
  if (input && String(input.value) !== String(value)) input.value = String(value);
  return value;
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
  const input = document.querySelector('#max-weight-input');
  const percent = clampNumber(input?.value, 1, 50, DASHBOARD_INPUT_DEFAULTS.maxWeightPercent);
  if (input && String(input.value) !== String(percent)) input.value = String(percent);
  return percent / 100;
}

function inputScenarioParameters() {
  const transactionCostBps = clampedTransactionCostBps();
  const slippageBps = clampedSlippageBps();
  return {
    lookbackMonths: selectedLookbackMonths(),
    topN: clampedTopN(),
    maxWeight: clampedMaxWeight(),
    rebalanceFrequency: selectedRebalanceFrequency(),
    transactionCostBps,
    slippageBps,
    totalCostRate: (transactionCostBps + slippageBps) / 10000,
  };
}

function rebalanceFrequencyLabel(value) {
  const labels = { W: '주간', ME: '월간', QE: '분기' };
  return labels[value] || value || '-';
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

function factorWeightSnapshot(run, date, windowKey, factor) {
  return (run.factor_weight_snapshots || []).find((snapshot) => (
    snapshot.date === date && snapshot.window === windowKey && snapshot.factor === factor
  )) || null;
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

function normalizeWeightRows(snapshot) {
  const rows = snapshot?.rows || [];
  return rows
    .map((row) => {
      if (Array.isArray(row)) return { symbol: row[0], weight: Number(row[1]), score: Number(row[2]) };
      return { symbol: row.symbol, weight: Number(row.weight ?? row.default_weight), score: Number(row.score) };
    })
    .filter((row) => row.symbol && Number.isFinite(row.weight) && row.weight > 0)
    .sort((a, b) => Number(b.weight) - Number(a.weight) || String(a.symbol).localeCompare(String(b.symbol)));
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

function topFactorsForDate(run, date, windowKey, limit = 10) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    return matrix.factors
      .map((factor, index) => ({
        factor,
        rank: index + 1,
        period_return: optionalNumber(matrix.returns?.[index]),
        window_label: matrix.window_label || windowKey,
        factor_count: matrix.factor_count || matrix.factors.length,
      }))
      .filter((row) => row.factor)
      .slice(0, limit);
  }
  return (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
    .slice(0, limit)
    .map((row, index) => ({
      factor: row.factor,
      rank: row.rank || index + 1,
      period_return: optionalNumber(row.period_return),
      window_label: row.window_label || windowKey,
      factor_count: row.factor_count || null,
    }))
    .filter((row) => row.factor);
}

function capAggregatedWeights(rows, maxWeight) {
  const cap = Math.max(0.01, Math.min(0.5, Number(maxWeight) || 0.1));
  const clean = rows
    .map((row) => ({ ...row, raw_ensemble_weight: Math.max(0, Number(row.raw_ensemble_weight) || 0) }))
    .filter((row) => row.symbol && row.raw_ensemble_weight > 0);
  const rawTotal = clean.reduce((sum, row) => sum + row.raw_ensemble_weight, 0);
  if (!clean.length || rawTotal <= 0) {
    return {
      rows: [],
      investedTotal: 0,
      cashTotal: 1,
      maxWeight: cap,
    };
  }
  const targetBudget = Math.min(1, rawTotal);
  const weights = clean.map((row) => row.raw_ensemble_weight * targetBudget / rawTotal);
  const active = new Set(clean.map((_, index) => index));
  let remainingBudget = targetBudget;
  while (active.size && remainingBudget > 1e-12) {
    const activeWeightTotal = [...active].reduce((sum, index) => sum + weights[index], 0);
    if (activeWeightTotal <= 0) break;
    const cappedThisRound = [];
    for (const index of active) {
      const candidateWeight = remainingBudget * (weights[index] / activeWeightTotal);
      if (candidateWeight > cap) {
        weights[index] = cap;
        cappedThisRound.push(index);
      }
    }
    if (!cappedThisRound.length) {
      for (const index of active) {
        weights[index] = remainingBudget * (weights[index] / activeWeightTotal);
      }
      remainingBudget = 0;
      break;
    }
    cappedThisRound.forEach((index) => {
      active.delete(index);
      remainingBudget -= weights[index];
    });
  }
  const cappedRows = clean.map((row, index) => ({
    ...row,
    display_weight: Math.max(0, weights[index] || 0),
    weight_cap: cap,
    weight_cap_excess: Math.max(0, (row.raw_ensemble_weight * targetBudget / rawTotal) - (weights[index] || 0)),
  }));
  const investedTotal = cappedRows.reduce((sum, row) => sum + row.display_weight, 0);
  return {
    rows: cappedRows,
    investedTotal,
    cashTotal: Math.max(0, 1 - investedTotal),
    maxWeight: cap,
  };
}

function topFactorEnsembleAllocation(run, date, windowKey, topN, maxWeight, factorLimit = 10) {
  const factorRows = topFactorsForDate(run, date, windowKey, factorLimit);
  const displayTopN = Math.max(1, Math.min(50, Math.round(Number(topN) || 20)));
  const sleeves = [];
  const missingFactors = [];
  factorRows.forEach((factorRow) => {
    const snapshot = factorWeightSnapshot(run, date, windowKey, factorRow.factor);
    const rows = normalizeWeightRows(snapshot);
    if (!rows.length) {
      missingFactors.push(factorRow.factor);
      return;
    }
    sleeves.push({ ...factorRow, snapshot, rows });
  });

  const bySymbol = new Map();
  const sleeveWeight = sleeves.length ? 1 / sleeves.length : 0;
  sleeves.forEach((sleeve) => {
    sleeve.rows.forEach((row) => {
      const key = String(row.symbol);
      const current = bySymbol.get(key) || {
        symbol: key,
        raw_ensemble_weight: 0,
        factor_count: 0,
        factors: [],
        score_sum: 0,
        best_score: Number.NEGATIVE_INFINITY,
        factor_weight_sum: 0,
      };
      const sleeveContribution = sleeveWeight * (Number(row.weight) || 0);
      current.raw_ensemble_weight += sleeveContribution;
      current.factor_weight_sum += Number(row.weight) || 0;
      current.factor_count += 1;
      current.factors.push(sleeve.factor);
      current.score_sum += Number(row.score) || 0;
      current.best_score = Math.max(current.best_score, Number(row.score) || Number.NEGATIVE_INFINITY);
      bySymbol.set(key, current);
    });
  });

  const capped = capAggregatedWeights([...bySymbol.values()], maxWeight);
  const allWeighted = capped.rows
    .sort((a, b) => (
      Number(b.display_weight) - Number(a.display_weight)
      || Number(b.factor_count) - Number(a.factor_count)
      || Number(b.score_sum) - Number(a.score_sum)
      || String(a.symbol).localeCompare(String(b.symbol))
    ));
  const weighted = allWeighted
    .slice(0, displayTopN)
    .map((row, index) => ({
      ...row,
      display_rank: index + 1,
      display_weight: Math.max(0, row.display_weight || 0),
      weighting_method: 'top_factor_equal_sleeve',
    }));

  return {
    weighted,
    topN: displayTopN,
    factorRows,
    sleeves,
    factorsUsedCount: sleeves.length,
    factorLimit,
    missingFactors,
    totalCandidateCount: bySymbol.size,
    hiddenWeight: allWeighted.slice(displayTopN).reduce((sum, row) => sum + (Number(row.display_weight) || 0), 0),
    investedTotal: capped.investedTotal,
    cashTotal: capped.cashTotal,
    maxWeight: capped.maxWeight,
    windowLabel: factorRows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
  };
}

function latestOutputFactor(run) {
  const rows = Array.isArray(run.latest_output_rows) ? run.latest_output_rows : [];
  if (!rows.length) return '';
  const rowFactors = [...new Set(rows.map((row) => row?.selected_factor).filter(Boolean))];
  if (rowFactors.length === 1) return rowFactors[0];
  if (rowFactors.length === 0) return run.summary?.selected_factor || '';
  return '';
}

function latestOutputMatchesFactor(run, factor) {
  const outputFactor = latestOutputFactor(run);
  return Boolean(outputFactor && factor && outputFactor === factor);
}

function latestOutputSignalRows(run, topN, factor = null) {
  if (factor && !latestOutputMatchesFactor(run, factor)) return [];
  const rows = Array.isArray(run.latest_output_rows) ? run.latest_output_rows : [];
  const count = Math.max(1, Math.min(50, Math.round(Number(topN) || 20), rows.length || 1));
  return rows.slice(0, count).map((row, index) => ({
    rank: row.rank || index + 1,
    symbol: row.symbol,
    score: optionalNumber(row.score),
    weight: optionalNumber(row.weight) || 0,
    pre_cap_weight: optionalNumber(row.pre_cap_weight ?? row.proposed_weight ?? row.weight) || 0,
    weighting_method: row.weighting_method || 'latest_output_rows',
    signal_date: row.signal_date || run.summary?.data_as_of || '-',
    selected_factor: row.selected_factor || run.summary?.selected_factor || '-',
  })).filter((row) => row.symbol);
}

function bestFactorSignalRows(run, date, windowKey, topN, maxWeight) {
  const best = periodBestStats(run, date, windowKey);
  const snapshot = best?.factor ? factorScoreSnapshot(run, date, best.factor) : null;
  const allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  const researchOnly = !isPracticalRun(run);
  const requestedTopN = Math.max(1, Math.min(50, Math.round(Number(topN) || 20)));
  let rows = allocation.weighted.map((row) => ({
    rank: row.display_rank,
    symbol: row.symbol,
    score: row.score,
    weight: researchOnly ? 0 : row.display_weight,
    pre_cap_weight: row.display_weight,
    weighting_method: 'best_factor_score_proportional_capped',
    signal_date: snapshot?.score_date || date,
    selected_factor: best?.factor || '-',
  }));
  let signalSource = 'best_factor_score_snapshot';
  if (!rows.length && Array.isArray(run.latest_output_rows) && run.latest_output_rows.length) {
    rows = latestOutputSignalRows(run, requestedTopN);
    signalSource = 'latest_output_rows_fallback';
  }
  return {
    rows,
    best,
    snapshot,
    allocation,
    researchOnly,
    signalSource,
    topN: signalSource === 'latest_output_rows_fallback' ? requestedTopN : allocation.topN,
    maxWeight: allocation.maxWeight,
    windowLabel: best?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
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

function humanSourceName(value) {
  const text = textValue(value);
  const labels = {
    'yfinance-adjusted-daily': 'yfinance 조정가격',
    'yahoo-chart-adjusted-daily-fallback': 'Yahoo chart 보강',
    'nasdaq-latest-close-repair': 'Nasdaq 최신일 보강',
    'stooq-daily-close-fallback': 'Stooq 대체',
    'finance-datareader-close-fallback': 'FinanceDataReader 대체',
    'yfinance-fast-info-market-cap': '시가총액 보강',
    'finviz-snapshot-market-cap': 'Finviz 시가총액 보강',
    'live-run-summary': '전체 실행 요약',
    'packaged-default-universe': '패키지 유니버스',
  };
  return labels[text] || text;
}

function formatCoverageMetric(ratio, numerator, denominator) {
  const ratioText = formatPercent(ratio);
  const num = Number(numerator);
  const den = Number(denominator);
  if (Number.isFinite(num) && Number.isFinite(den) && den > 0) {
    return `${ratioText} (${formatInteger(num)} / ${formatInteger(den)})`;
  }
  return ratioText;
}

function formatSourceHealth(rows) {
  if (!Array.isArray(rows) || !rows.length) return '-';
  return rows
    .filter((row) => row && row.source)
    .slice(0, 8)
    .map((row) => {
      const parts = [];
      if (Number(row.success_rows) > 0) parts.push(`성공 ${formatInteger(row.success_rows)}`);
      if (Number(row.no_newer_rows) > 0) parts.push(`추가 없음 ${formatInteger(row.no_newer_rows)}`);
      if (Number(row.failed_rows) > 0) parts.push(`실패 ${formatInteger(row.failed_rows)}`);
      if (!parts.length) parts.push(`행 ${formatInteger(row.row_count)}`);
      return `${humanSourceName(row.source)}: ${parts.join(', ')}`;
    })
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

function scenarioAllocationForFactor(run, date, windowKey, factor, topN, maxWeight) {
  const snapshot = factorScoreSnapshot(run, date, factor);
  let allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  let fallbackSource = null;
  if (!allocation.weighted.length) {
    const weightSnapshot = factorWeightSnapshot(run, date, windowKey, factor);
    const weightRows = normalizeWeightRows(weightSnapshot).map((row) => ({
      symbol: row.symbol,
      score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.weight) || 0,
    }));
    allocation = computeScenarioAllocation(weightRows, topN, maxWeight);
    if (allocation.weighted.length) fallbackSource = 'factor_weight_snapshot_fallback';
  }
  if (!allocation.weighted.length) {
    const holdingRows = (run.holdings || [])
      .filter((row) => row.date === date && row.window === windowKey && row.factor === factor)
      .map((row) => ({
        symbol: row.symbol,
        score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.default_weight) || 0,
      }));
    allocation = computeScenarioAllocation(holdingRows, topN, maxWeight);
    if (allocation.weighted.length) fallbackSource = 'holding_rows_fallback';
  }
  const latestOutputRowsFactor = latestOutputFactor(run);
  if (
    !allocation.weighted.length
    && Array.isArray(run.latest_output_rows)
    && run.latest_output_rows.length
    && latestOutputMatchesFactor(run, factor)
  ) {
    const fallbackRows = latestOutputSignalRows(run, topN, factor).map((row, index) => {
      const displayWeight = Math.max(0, Math.min(maxWeight, optionalNumber(row.pre_cap_weight) || optionalNumber(row.weight) || 0));
      return {
        ...row,
        display_rank: row.rank || index + 1,
        display_weight: displayWeight,
        scenario_weight: displayWeight,
      };
    });
    const investedTotal = fallbackRows.reduce((sum, row) => sum + (Number(row.display_weight) || 0), 0);
    allocation = {
      weighted: fallbackRows,
      investedTotal,
      displayedTotal: investedTotal,
      portfolioTotal: investedTotal,
      cashTotal: Math.max(0, 1 - investedTotal),
      unusedCandidateCount: Math.max(0, (run.latest_output_rows || []).length - fallbackRows.length),
      weightingMethod: 'latest_output_rows_fallback',
      topN: Math.max(1, Math.min(50, Math.round(Number(topN) || DASHBOARD_INPUT_DEFAULTS.topN))),
      maxWeight,
      availableCount: fallbackRows.length,
    };
    fallbackSource = 'latest_output_rows_fallback';
  }
  return { allocation, snapshot, fallbackSource, latestOutputRowsFactor };
}

function currentWeightedHoldings() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const { allocation, snapshot, fallbackSource, latestOutputRowsFactor } = scenarioAllocationForFactor(run, date, windowKey, factor, topN, maxWeight);
  const availableDates = factorAvailableDates(run, factor);
  const stats = periodFactorStats(run, date, windowKey, factor);
  return {
    ...allocation,
    snapshot,
    selectedFactor: factor || '-',
    windowLabel: stats?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
    scoreDate: snapshot?.score_date || (fallbackSource ? run.summary?.data_as_of || null : null),
    scoreScope: snapshot?.score_scope || fallbackSource,
    latestOutputRowsFactor,
    rawAvailableCount: snapshot?.raw_available_count ?? null,
    eligibilityFilterApplied: snapshot?.eligibility_filter_applied === true,
    missingReason: snapshot
      ? null
      : fallbackSource
      ? null
      : latestOutputRowsFactor && factor && latestOutputRowsFactor !== factor
      ? `저장된 latest_output_rows는 ${latestOutputRowsFactor} 기준이라 선택 팩터 ${factor} 시나리오로 표시하지 않습니다.`
      : availableDates.size && !availableDates.has(date)
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
  const hasFactorSpecificDates = Object.keys(byFactor).length > 0;
  const dates = [...(hasFactorSpecificDates ? (byFactor[factor] || []) : (run.scenario_available_dates || []))];
  if (!dates.length && latestOutputMatchesFactor(run, factor) && run.summary?.data_as_of) {
    dates.push(run.summary.data_as_of);
  }
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

function factorOptionLabel(item, bestDefaultFactor, run) {
  if (item.factor === bestDefaultFactor) return `${item.factor} · 현재 기준 최고 팩터`;
  if (item.factor === run.summary?.selected_factor) return `${item.factor} · 실행 저장 선택`;
  return `${item.factor} · ${humanFactorCategory(item.category)}`;
}

function updateFactorOptionLabels(run, bestDefaultFactor) {
  const factorSelect = document.querySelector('#factor-select');
  if (!factorSelect) return;
  const metadata = new Map(factorOptions(run).map((item) => [item.factor, item]));
  Array.from(factorSelect.children || []).forEach((option) => {
    const item = metadata.get(option.value) || { factor: option.value, category: 'unknown' };
    option.textContent = factorOptionLabel(item, bestDefaultFactor, run);
  });
}

function syncDefaultFactorToCurrentBasis() {
  if (state.hasUserSelectedFactor) return;
  const run = currentRun();
  const factorSelect = document.querySelector('#factor-select');
  if (!run || !factorSelect) return;
  const bestDefaultFactor = periodBestStats(run, selectedDate(), selectedWindow())?.factor;
  updateFactorOptionLabels(run, bestDefaultFactor);
  const values = Array.from(factorSelect.children || []).map((option) => option.value);
  if (bestDefaultFactor && values.includes(bestDefaultFactor)) {
    factorSelect.value = bestDefaultFactor;
    fillDateOptions(run, selectedDate());
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
  const windows = run.periods || [];
  const windowSelect = document.querySelector('#window-select');
  const previousWindow = windowSelect?.value || '';
  windowSelect.replaceChildren();
  windows.forEach((period) => {
    const option = document.createElement('option');
    option.value = period.key;
    option.textContent = period.label;
    windowSelect.appendChild(option);
  });
  const windowKeys = windows.map((period) => period.key);
  const defaultWindow = windowKeys.includes(DASHBOARD_INPUT_DEFAULTS.window)
    ? DASHBOARD_INPUT_DEFAULTS.window
    : (windowKeys.includes('1Y') ? '1Y' : (windowKeys.at(-1) || windowKeys[0] || '1M'));
  windowSelect.value = windowKeys.includes(previousWindow) ? previousWindow : defaultWindow;

  const previousDate = document.querySelector('#date-select')?.value || null;
  fillDateOptions(run, previousDate);
  const dateForDefault = selectedDate();

  const factorSelect = document.querySelector('#factor-select');
  const previousFactor = state.hasUserSelectedFactor ? factorSelect?.value || '' : '';
  factorSelect.replaceChildren();
  const options = factorOptions(run);
  const bestDefaultFactor = periodBestStats(run, dateForDefault, windowSelect.value)?.factor;
  options.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.factor;
    option.textContent = factorOptionLabel(item, bestDefaultFactor, run);
    factorSelect.appendChild(option);
  });
  const factors = options.map((item) => item.factor);
  factorSelect.value = previousFactor && factors.includes(previousFactor)
    ? previousFactor
    : (factors.includes(bestDefaultFactor) ? bestDefaultFactor : (factors.includes(run.summary?.selected_factor) ? run.summary.selected_factor : factors[0] || ''));

  fillDateOptions(run, selectedDate());
  document.querySelector('#topn-input').value = DASHBOARD_INPUT_DEFAULTS.topN;
  document.querySelector('#max-weight-input').value = DASHBOARD_INPUT_DEFAULTS.maxWeightPercent;
  const lookback = document.querySelector('#lookback-months-select');
  if (lookback) lookback.value = String(DASHBOARD_INPUT_DEFAULTS.lookbackMonths);
  const rebalance = document.querySelector('#rebalance-select');
  if (rebalance) rebalance.value = DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
  const transactionCost = document.querySelector('#transaction-cost-input');
  if (transactionCost) transactionCost.value = String(DASHBOARD_INPUT_DEFAULTS.transactionCostBps);
  const slippage = document.querySelector('#slippage-input');
  if (slippage) slippage.value = String(DASHBOARD_INPUT_DEFAULTS.slippageBps);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const params = inputScenarioParameters();
  const scenarioRows = scenarioPeriodRows(run, date, windowKey, params);
  const best = scenarioRows[0] || scenarioBestStats(run, date, windowKey, params);
  const factor = selectedFactor();
  const selectedStats = scenarioRows.find((row) => row.factor === factor) || scenarioFactorStats(run, date, windowKey, factor, params);
  const summary = run.summary || {};
  const latestRunAt = formatKoreanDateTime(summary.run_timestamp_utc);
  const runPayloadGeneratedAtText = formatKoreanDateTime(runPayloadGeneratedAt(run));
  setText('#best-factor', best?.factor || '-');
  setText(
    '#best-factor-detail',
    best
      ? `${best.window_label} 브라우저 시나리오 수익률 ${formatPercent(best.period_return)}${best.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(best.raw_period_return)}` : ''}`
      : '-',
  );
  setText('#selected-factor', factor || '-');
  setText(
    '#selected-factor-detail',
    selectedStats && selectedStats.rank
      ? `${selectedStats.window_label} 브라우저 시나리오 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'} · ${formatPercent(selectedStats.period_return)}${selectedStats.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(selectedStats.raw_period_return)}` : ''} · ${factorDescription(factor, run)}`
      : `자료 없음 · ${factorDescription(factor, run)}`,
  );
  setText('#recommendation-status', humanStatus(summary.recommendation_status, summary.recommendation_output_label));
  setText('#data-provider', `기준일 ${summary.data_as_of || '-'} · ${humanProvider(summary.provider)}`);
  setText('#latest-run-at', latestRunAt);
  setText('#latest-run-detail', `분석 실행 기준 · 실행 결과 생성 ${runPayloadGeneratedAtText}`);
  const scenario = currentWeightedHoldings();
  setText(
    '#scenario-live-summary',
    `브라우저 시나리오/프록시 입력 · 최근 ${params.lookbackMonths}개월 · 상위 ${params.topN}개 · 종목당 최대 ${formatPercent(params.maxWeight)} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 리밸런싱 · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps · 시나리오 투자 ${formatPercent(scenario.investedTotal)} · 현금/미사용 ${formatPercent(scenario.cashTotal)}`,
  );

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
  appendDefinition(dataSummary, '모형 가격 보유 종목', formatCount(quality.fetched_price_symbol_count));
  appendDefinition(dataSummary, '제외 종목 수', formatCount(quality.excluded_symbols));
  appendDefinition(
    dataSummary,
    '요청 가격 커버리지',
    formatCoverageMetric(
      quality.price_coverage_ratio,
      quality.provider_returned_symbol_count,
      quality.provider_requested_symbol_count,
    ),
  );
  appendDefinition(
    dataSummary,
    '모형 가격 보유 비율',
    formatCoverageMetric(
      quality.model_price_universe_ratio,
      quality.fetched_price_symbol_count,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '가격 적격 비율',
    formatCoverageMetric(
      quality.eligible_price_ratio,
      summary.eligible_price_universe_size ?? quality.eligible_price_universe_size,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '유동성 적격 비율',
    formatCoverageMetric(
      quality.liquidity_eligible_ratio,
      summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '신선 가격 비율',
    formatCoverageMetric(quality.fresh_price_ratio, quality.fresh_price_rows, quality.price_quality_rows),
  );
  appendDefinition(dataSummary, '데이터 기준일', quality.data_as_of || summary.data_as_of || '-');
  appendDefinition(dataSummary, '최근 실행 시각', formatKoreanDateTime(summary.run_timestamp_utc));
  appendDefinition(dataSummary, '실행 결과 생성 시각', formatKoreanDateTime(runPayloadGeneratedAt(run)));
  appendDefinition(dataSummary, '가격 제공자', humanProvider(quality.provider || summary.provider));
  appendDefinition(dataSummary, '소스별 수집 상태', formatSourceHealth(quality.source_health));
  appendDefinition(
    dataSummary,
    '가격 소스 분포',
    formatCounts(quality.price_source_counts, {
      'yfinance-adjusted-daily': 'yfinance',
      'yahoo-chart-adjusted-daily-fallback': 'Yahoo chart',
      'nasdaq-latest-close-repair': 'Nasdaq 보강',
      'stooq-daily-close-fallback': 'Stooq',
      'finance-datareader-close-fallback': 'FinanceDataReader',
    }),
  );
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
  const params = inputScenarioParameters();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const scenarioRows = scenarioPeriodRows(run, row.date, row.window, params);
    const bestStats = scenarioRows[0] || periodBestStats(run, row.date, row.window);
    const selectedStats = scenarioRows.find((item) => item.factor === factor) || scenarioFactorStats(run, row.date, row.window, factor, params);
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, bestStats?.factor || row.best_factor);
    appendCell(tr, bestStats?.period_return == null ? '자료 없음' : `${formatPercent(bestStats.period_return)} · 시나리오`, { className: classForNumber(bestStats?.period_return) });
    appendCell(tr, selectedStats?.period_return == null ? '자료 없음' : `${formatPercent(selectedStats.period_return)} · 시나리오`, { className: classForNumber(selectedStats?.period_return) });
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
    scoreScope,
    unusedCandidateCount,
    maxWeight,
    rawAvailableCount,
    eligibilityFilterApplied,
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
  const usingLatestOutputFallback = scoreScope === 'latest_output_rows_fallback';
  const scopeNote = usingLatestOutputFallback
    ? `점수 스냅샷이 없어 저장된 latest_output_rows ${formatInteger(availableCount)}개를 선택 팩터 시나리오 fallback으로 표시합니다.`
    : eligibilityFilterApplied
    ? `현재 모델 편입 가능 필터를 통과한 ${formatInteger(availableCount)}개 후보를 사용합니다${rawAvailableCount && rawAvailableCount !== availableCount ? ` (원점수 후보 ${formatInteger(rawAvailableCount)}개 중 실무 필터 통과분)` : ''}.`
    : `편입 가능 필터 정보가 없어 원점수 후보 ${formatInteger(availableCount)}개를 연구 진단용으로 표시합니다.`;
  setText(
    '#holdings-availability',
    missingReason
      ? `${missingReason} 기간 최고 팩터 보유를 대신 보여주지 않습니다.`
      : run.history_payload_type === 'summary'
      ? '이전 실행은 페이지 속도를 위해 요약 이력만 보관합니다. 상위 종목과 비중은 최신 실행에서 전체 표시됩니다.'
      : usingLatestOutputFallback
      ? `${windowLabel} 선택 팩터 ${factor}의 점수 스냅샷이 없어 기존 최신 출력 행 기준입니다. ${scopeNote} 상위 ${Math.min(topN, availableCount)}개를 표시하며, 저장된 게이트 전 비중을 종목당 최대 ${formatPercent(maxWeight)}로 제한해 표시합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`
      : `${windowLabel} 선택 팩터 ${factor}의 ${scoreDate || '최근'} 점수 스냅샷 기준입니다. ${scopeNote} 상위 ${Math.min(topN, availableCount)}개를 표시하며, ${weightLabel}은 브라우저가 팩터 점수 비례 배분과 종목당 최대 ${formatPercent(maxWeight)} 가정으로 계산합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`,
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
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const {
    rows,
    best,
    snapshot,
    allocation,
    researchOnly,
    signalSource,
    windowLabel,
  } = bestFactorSignalRows(run, date, windowKey, topN, maxWeight);
  const tbody = document.querySelector('#current-output-table tbody');
  const note = document.querySelector('#current-output-note');
  tbody.replaceChildren();
  if (note) {
    const blockers = joinReasonList(summary.tradability_blockers) || joinReasonList(summary.fail_closed_reasons) || '실전 매매 게이트 미통과';
    const candidateCount = formatCount(summary.candidate_universe_size ?? quality.candidate_universe_size);
    const eligibleCount = formatCount(summary.eligible_price_universe_size ?? quality.eligible_price_universe_size);
    const liquidityCount = formatCount(summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size);
    const usingLatestOutputFallback = signalSource === 'latest_output_rows_fallback';
    const scope = usingLatestOutputFallback
      ? `${run.summary?.data_as_of || date || '-'} · 기존 최신 출력 행`
      : best?.factor
      ? `${date || '-'} · ${windowLabel} 최고 팩터 ${best.factor}`
      : `${date || '-'} · ${windowLabel} 최고 팩터 자료 없음`;
    const availability = usingLatestOutputFallback
      ? `최고 팩터 점수 스냅샷이 없어 저장된 latest_output_rows ${formatInteger(rows.length)}개를 투명한 fallback으로 표시합니다.`
      : snapshot
      ? `모델 편입 가능 후보 ${formatInteger(allocation.availableCount)}개 중 상위 ${rows.length}개를 표시합니다.`
      : '해당 최고 팩터의 종목 점수 스냅샷이 없어 행을 표시하지 못했습니다.';
    const bestFactorCaution = 'Best factor는 해당 기간의 과거 성과 1위 팩터이므로 미래 우위를 보장하지 않으며, 선택 팩터 드롭다운과 별개입니다.';
    note.textContent = researchOnly
      ? `${scope} · 연구용 신호(매매 비중 0%). ${availability} ${bestFactorCaution} 미충족: ${blockers}. 후보 ${candidateCount} · 가격 적격 ${eligibleCount} · 유동성 적격 ${liquidityCount}.`
      : `${scope} 기준 표시용 best-factor 신호입니다. ${availability} ${bestFactorCaution} 후보 ${candidateCount}, 가격 적격 ${eligibleCount}, 유동성 적격 ${liquidityCount}.`;
  }
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.textContent = '선택한 기준일과 기간의 최고 팩터에 표시할 신호 스냅샷이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.rank || index + 1);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, row.selected_factor || best?.factor || '-');
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
  const params = inputScenarioParameters();
  let rows = scenarioPeriodRows(run, date, windowKey, params);
  const best = rows[0] || scenarioBestStats(run, date, windowKey, params);
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 10);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText(
    '#factor-chart-meta',
    `${date || '-'} · ${windowLabel} · 브라우저 시나리오/프록시 · 최근 ${params.lookbackMonths}개월 · 선택 ${factor || '-'} · 상위 ${params.topN}개 · 최대 ${formatPercent(params.maxWeight)} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps`,
  );
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(
    target,
    `${row.rank}. ${row.factor}`,
    `${formatPercent(row.period_return)}${row.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(row.raw_period_return)}` : ''}`,
    row.period_return,
    maxAbs,
    { className: `${row.factor === factor ? 'is-selected' : ''} ${row.factor === best?.factor ? 'is-best' : ''}`.trim() },
  ));
  const note = document.createElement('div');
  note.className = 'scenario-note';
  const fallbackCount = rows.filter((row) => !row.scenario_adjusted).length;
  note.textContent = `막대값은 저장된 팩터 누적성과를 현재 입력값의 비중 집중도·리밸런싱·거래비용 가정으로 조정한 브라우저 시나리오/민감도 프록시입니다.${fallbackCount ? ` ${fallbackCount}개 팩터는 필요한 백테스트 시계열이 부족해 원자료 수익률 fallback을 사용했습니다.` : ''}`;
  target.appendChild(note);
  if (!selectedRow) {
    const missingNote = document.createElement('div');
    missingNote.className = 'scenario-note';
    missingNote.textContent = '선택 팩터가 이 기준일/기간의 내보낸 순위 데이터에 없습니다. 팩터 비교는 가능한 데이터 범위 안에서만 표시됩니다.';
    target.appendChild(missingNote);
  }
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const selectedFactorName = selectedFactor();
  const params = inputScenarioParameters();
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
    const scenarioRows = scenarioPeriodRows(run, row.date, row.window, params);
    const best = scenarioRows[0] || periodBestStats(run, row.date, row.window);
    const selectedStats = scenarioRows.find((item) => item.factor === selectedFactorName) || scenarioFactorStats(run, row.date, row.window, selectedFactorName, params);
    const factorNode = document.createElement('strong');
    factorNode.textContent = best?.factor || row.best_factor || '-';
    const detail = document.createElement('small');
    detail.textContent = selectedStats?.rank
      ? `브라우저 시나리오 최고 ${formatPercent(best?.period_return)} · 선택 팩터 ${formatPercent(selectedStats.period_return)} · 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'}`
      : `브라우저 시나리오 최고 ${formatPercent(best?.period_return)} · 선택 팩터 자료 없음`;
    chip.append(label, factorNode, detail);
    target.appendChild(chip);
  });
}

function renderLeaderTrendChart() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const params = inputScenarioParameters();
  const rows = (run.factor_leaders || [])
    .filter((row) => row.window === windowKey)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .slice(-30)
    .map((row) => {
      const best = scenarioBestStats(run, row.date, row.window, params);
      return {
        ...row,
        best_factor: best?.factor || row.best_factor,
        best_return: best?.period_return ?? row.best_return,
        scenario_adjusted: best?.scenario_adjusted === true,
      };
    });
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
    bar.title = `${row.date} · ${row.best_factor} · ${formatPercent(row.best_return)} · 브라우저 시나리오/프록시`;
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
  setText('#weight-chart-meta', `${isPracticalRun(run) ? '투자 시나리오' : '연구 시나리오'} · 선택 팩터 ${selectedFactor() || '-'} · 상위 ${topN}개 · 최대 ${formatPercent(maxWeight)}`);
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

function renderEnsembleWeightChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const target = document.querySelector('#ensemble-weight-chart');
  target.replaceChildren();
  const ensemble = topFactorEnsembleAllocation(run, date, windowKey, topN, maxWeight, 10);
  setText(
    '#ensemble-chart-meta',
    `${date || '-'} · ${ensemble.windowLabel} · ${ensemble.factorsUsedCount}/${Math.min(10, ensemble.factorRows.length)}개 팩터 · 최종 상한 ${formatPercent(ensemble.maxWeight)}`,
  );
  if (!ensemble.weighted.length) {
    appendEmpty(
      '#ensemble-weight-chart',
      '선택한 기준일과 기간에 상위 팩터의 백테스트 보유 비중 스냅샷이 없어 합산 비중을 표시할 수 없습니다.',
    );
    return;
  }
  const maxWeightValue = Math.max(
    ...ensemble.weighted.map((row) => Number(row.display_weight) || 0),
    0.01,
  );
  ensemble.weighted.forEach((row) => {
    const label = `${row.symbol} · ${row.factor_count}개 팩터`;
    appendBarRow(target, label, formatPercent(row.display_weight), row.display_weight, maxWeightValue);
  });
  const factorNames = ensemble.sleeves.map((sleeve) => `${sleeve.rank}. ${sleeve.factor}`).join(', ');
  const note = document.createElement('div');
  note.className = 'scenario-note';
  const missing = ensemble.missingFactors.length
    ? ` 스냅샷이 없는 팩터 ${ensemble.missingFactors.length}개는 제외했습니다.`
    : '';
  note.textContent = `해석: ${ensemble.windowLabel} 성과 상위 팩터들을 각각 같은 팩터별 포트폴리오 비중으로 보고, 각 팩터 내부는 기존 백테스트 일별 보유 비중을 그대로 사용한 뒤 중복 종목 비중을 합산했습니다. 합산 후 브라우저 종목당 최대 비중 ${formatPercent(ensemble.maxWeight)}를 최종 상한으로 적용했습니다. 시각화는 개별 종목 ${ensemble.weighted.length}개만 표시하고, 미표시 후보 합계 ${formatPercent(ensemble.hiddenWeight)} 및 현금/상한 미사용 ${formatPercent(ensemble.cashTotal)}는 숫자로만 제공합니다. 전체 합산 후보 ${ensemble.totalCandidateCount}개. 사용 팩터: ${factorNames}.${missing}`;
  target.appendChild(note);
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

function lookbackFilteredPoints(points, months) {
  if (!points.length) return [];
  const endDate = parseDateString(points.at(-1).date);
  if (!endDate) return points;
  const cutoff = new Date(endDate.getTime());
  cutoff.setUTCMonth(cutoff.getUTCMonth() - Math.max(1, Number(months) || DASHBOARD_INPUT_DEFAULTS.lookbackMonths));
  const filtered = points.filter((point) => {
    const pointDate = parseDateString(point.date);
    return pointDate && pointDate >= cutoff;
  });
  return filtered.length >= 2 ? filtered : points.slice(-Math.min(points.length, 2));
}

function rebalanceBucket(dateText, frequency) {
  const parts = String(dateText || '').split('-').map((part) => Number(part));
  if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return String(dateText || '');
  const [year, month, day] = parts;
  if (frequency === 'QE') return `${year}-Q${Math.floor((month - 1) / 3) + 1}`;
  if (frequency === 'W') return `${year}-${String(month).padStart(2, '0')}-W${Math.ceil(day / 7)}`;
  return `${year}-${String(month).padStart(2, '0')}`;
}

function isScenarioRebalance(points, index, frequency) {
  if (index <= 0 || index >= points.length) return false;
  return rebalanceBucket(points[index].date, frequency) !== rebalanceBucket(points[index - 1].date, frequency);
}

function allocationConcentration(allocation) {
  const weights = (allocation?.weighted || []).map((row) => Number(row.display_weight) || 0).filter((value) => value > 0);
  if (!weights.length) return 0;
  return weights.reduce((sum, value) => sum + value * value, 0);
}

function adjustedScenarioPointsFromRaw(rawPoints, params, allocation) {
  if (rawPoints.length < 2) return rawPoints;
  const hasAllocation = Array.isArray(allocation?.weighted) && allocation.weighted.length > 0;
  const invested = hasAllocation ? Math.max(0, Math.min(1, Number(allocation?.investedTotal) || 0)) : 1;
  const topN = Math.max(1, Number(params.topN) || DASHBOARD_INPUT_DEFAULTS.topN);
  const concentration = hasAllocation ? allocationConcentration(allocation) : 1 / topN;
  const equalConcentration = 1 / topN;
  const concentrationTilt = Math.max(-0.5, Math.min(2.5, concentration / Math.max(equalConcentration, 1e-6) - 1));
  const exposureMultiplier = Math.max(0.05, Math.min(1.45, invested * (1 + 0.10 * concentrationTilt)));
  const turnoverProxy = Math.max(0, Math.min(2, 0.35 + 0.20 * Math.max(0, concentrationTilt)));
  const adjusted = [{ ...rawPoints[0], equity: 1, drawdown: 0 }];
  let equity = 1;
  let peak = 1;
  for (let index = 1; index < rawPoints.length; index += 1) {
    const previous = Number(rawPoints[index - 1].equity);
    const current = Number(rawPoints[index].equity);
    let dailyReturn = previous > 0 && Number.isFinite(previous) && Number.isFinite(current)
      ? current / previous - 1
      : 0;
    dailyReturn *= exposureMultiplier;
    if (isScenarioRebalance(rawPoints, index, params.rebalanceFrequency)) {
      dailyReturn -= turnoverProxy * params.totalCostRate;
    }
    equity *= Math.max(0.0001, 1 + dailyReturn);
    peak = Math.max(peak, equity);
    adjusted.push({
      date: rawPoints[index].date,
      equity,
      drawdown: peak > 0 ? equity / peak - 1 : 0,
      scenario_exposure: exposureMultiplier,
      scenario_turnover_proxy: turnoverProxy,
    });
  }
  return adjusted;
}

function scenarioAdjustedSeriesPoints(series, date, params, allocation) {
  const rawPoints = lookbackFilteredPoints(seriesPointsThroughDate(series, date, 2000), params.lookbackMonths);
  return adjustedScenarioPointsFromRaw(rawPoints, params, allocation);
}

function tradingDaysForWindow(run, windowKey) {
  const period = (run.periods || []).find((item) => item.key === windowKey);
  const days = Number(period?.trading_days);
  if (Number.isFinite(days) && days > 0) return Math.round(days);
  const fallback = { '1W': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252 };
  return fallback[windowKey] || Math.max(21, Math.round((Number(inputScenarioParameters().lookbackMonths) || 12) * 21));
}

function scenarioLookbackTradingDays(params) {
  const months = Number(params?.lookbackMonths);
  if (!Number.isFinite(months) || months <= 0) return null;
  return Math.max(1, Math.round(months * 21));
}

function scenarioWindowTradingDays(run, windowKey, params) {
  const windowDays = tradingDaysForWindow(run, windowKey);
  const lookbackDays = scenarioLookbackTradingDays(params);
  return lookbackDays ? Math.max(1, Math.min(windowDays, lookbackDays)) : windowDays;
}

function scenarioAdjustedWindowPoints(run, factor, date, windowKey, params, allocation) {
  const series = factorBacktestSeries(run, factor);
  const rawPoints = lookbackFilteredPoints(seriesPointsThroughDate(series, date, 2000), params.lookbackMonths);
  if (rawPoints.length < 2) return [];
  const tradingDays = scenarioWindowTradingDays(run, windowKey, params);
  const windowPoints = rawPoints.slice(-Math.min(rawPoints.length, tradingDays + 1));
  return adjustedScenarioPointsFromRaw(windowPoints, params, allocation);
}

function cumulativeReturnFromPoints(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const first = Number(points[0].equity);
  const last = Number(points.at(-1).equity);
  if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
  return last / first - 1;
}

function rawPeriodRows(run, date, windowKey) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    return matrix.factors.map((name, index) => ({
      factor: name,
      raw_rank: index + 1,
      rank: index + 1,
      period_return: optionalNumber(matrix.returns?.[index]),
      raw_period_return: optionalNumber(matrix.returns?.[index]),
      window_label: matrix.window_label || windowKey,
      factor_count: matrix.factor_count || matrix.factors.length,
    }));
  }
  return (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .map((row, index) => ({
      factor: row.factor,
      raw_rank: row.rank || index + 1,
      rank: row.rank || index + 1,
      period_return: optionalNumber(row.period_return),
      raw_period_return: optionalNumber(row.period_return),
      window_label: row.window_label || windowKey,
      factor_count: row.factor_count || null,
    }));
}

function scenarioFactorStats(run, date, windowKey, factor, params = inputScenarioParameters()) {
  const rawStats = periodFactorStats(run, date, windowKey, factor) || { factor, rank: null, period_return: null };
  const allocation = scenarioAllocationForFactor(run, date, windowKey, factor, params.topN, params.maxWeight).allocation;
  const points = scenarioAdjustedWindowPoints(run, factor, date, windowKey, params, allocation);
  const scenarioReturn = cumulativeReturnFromPoints(points);
  return {
    ...rawStats,
    factor,
    raw_period_return: rawStats?.period_return ?? null,
    period_return: scenarioReturn ?? rawStats?.period_return ?? null,
    scenario_adjusted: scenarioReturn !== null,
    scenario_points: points,
    scenario_allocation: allocation,
    scenario_inputs: params,
  };
}

function scenarioPeriodRows(run, date, windowKey, params = inputScenarioParameters()) {
  const rows = rawPeriodRows(run, date, windowKey);
  const enhanced = rows.map((row) => {
    const scenario = scenarioFactorStats(run, date, windowKey, row.factor, params);
    return {
      ...row,
      raw_period_return: row.raw_period_return ?? row.period_return,
      period_return: scenario.period_return,
      scenario_adjusted: scenario.scenario_adjusted,
      scenario_points: scenario.scenario_points,
      scenario_allocation: scenario.scenario_allocation,
    };
  });
  return enhanced
    .sort((a, b) => {
      const ar = Number(a.period_return);
      const br = Number(b.period_return);
      if (Number.isFinite(ar) && Number.isFinite(br) && ar !== br) return br - ar;
      if (Number.isFinite(br) !== Number.isFinite(ar)) return Number.isFinite(br) ? 1 : -1;
      return Number(a.raw_rank || 9999) - Number(b.raw_rank || 9999);
    })
    .map((row, index) => ({
      ...row,
      rank: index + 1,
      factor_count: row.factor_count || enhanced.length,
    }));
}

function scenarioBestStats(run, date, windowKey, params = inputScenarioParameters()) {
  return scenarioPeriodRows(run, date, windowKey, params)[0] || periodBestStats(run, date, windowKey);
}

function renderBacktestChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const benchmark = benchmarkBacktestSeries(run);
  const params = inputScenarioParameters();
  const best = scenarioBestStats(run, date, windowKey, params);
  const selectedAllocation = scenarioAllocationForFactor(run, date, windowKey, factor, params.topN, params.maxWeight).allocation;
  const selectedSeries = normalizedLine(scenarioAdjustedSeriesPoints(factorBacktestSeries(run, factor), date, params, selectedAllocation));
  const bestAllocation = best?.factor
    ? scenarioAllocationForFactor(run, date, windowKey, best.factor, params.topN, params.maxWeight).allocation
    : null;
  const bestMetricSeries = best?.factor
    ? normalizedLine(scenarioAdjustedSeriesPoints(factorBacktestSeries(run, best.factor), date, params, bestAllocation))
    : [];
  const bestSeries = best?.factor && best.factor !== factor ? bestMetricSeries : [];
  const benchmarkSeries = normalizedLine(lookbackFilteredPoints(seriesPointsThroughDate(benchmark, date, 2000), params.lookbackMonths));
  const benchmarkLabel = benchmark?.label_ko || benchmark?.symbol || run.summary?.chart_benchmark || '나스닥 벤치마크';
  const target = document.querySelector('#backtest-chart');
  target.replaceChildren();
  setText(
    '#backtest-chart-meta',
    `${date || '-'} 기준 · 브라우저 프록시/민감도 뷰 · 최근 ${params.lookbackMonths}개월 · 선택 ${factor || '-'}${best?.factor ? ` · 기간 최고 ${best.factor}` : ''}${benchmarkSeries.length ? ` · 벤치마크 ${benchmarkLabel}` : ''} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps · 최대 ${formatPercent(params.maxWeight)} · 저장된 팩터 곡선을 현재 비중 집중도와 비용 가정으로 조정`
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
  title.textContent = '기간별 프록시 성과 지표 비교';
  const note = document.createElement('p');
  note.textContent = '각 기간 카드에서 같은 지표의 선택 팩터·기간 최고 팩터·나스닥 값을 한 줄로 비교합니다. 선택/기간 최고 팩터 값은 새 백엔드 재백테스트가 아니라 저장된 팩터 누적 성과를 현재 입력값의 비중 집중도·리밸런싱·비용 가정으로 조정한 브라우저 프록시입니다. 샤프·변동성·소르티노·칼마·CVaR 산식은 같은 방식으로 적용하고, CVaR은 최악 5% 일간 손실 평균입니다. 실제 일별 구성종목 재매매 결과로 해석하지 마세요.';
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

function normalizeDailyActualRows(sourceRows, sourceMeta = {}) {
  return (sourceRows || [])
    .map((row, index) => {
      if (Array.isArray(row)) {
        return {
          date: sourceMeta.date || '-',
          window: sourceMeta.window || '-',
          windowLabel: sourceMeta.window_label || sourceMeta.window || '-',
          factor: sourceMeta.factor || '-',
          rank: index + 1,
          symbol: row[0],
          actualWeight: Number(row[1]),
          score: Number(row[2]),
          weightDate: sourceMeta.weight_date || sourceMeta.date || '-',
          scoreDate: sourceMeta.score_date || sourceMeta.date || '-',
          source: sourceMeta.weight_source || '백테스트 일별 보유 비중',
        };
      }
      return {
        date: row.date || sourceMeta.date || '-',
        window: row.window || sourceMeta.window || '-',
        windowLabel: row.window_label || sourceMeta.window_label || row.window || '-',
        factor: row.factor || sourceMeta.factor || '-',
        rank: row.rank || index + 1,
        symbol: row.symbol,
        actualWeight: Number(row.default_weight ?? row.weight),
        score: Number(row.score),
        weightDate: row.weight_date || sourceMeta.weight_date || row.date || sourceMeta.date || '-',
        scoreDate: row.score_date || sourceMeta.score_date || row.date || sourceMeta.date || '-',
        source: row.weight_source || sourceMeta.weight_source || '백테스트 일별 보유 비중',
      };
    })
    .filter((row) => row.symbol && Number.isFinite(row.actualWeight) && row.actualWeight > 0)
    .sort((a, b) => (
      String(b.date).localeCompare(String(a.date))
      || Number(a.rank || 9999) - Number(b.rank || 9999)
      || Number(b.actualWeight) - Number(a.actualWeight)
    ));
}

function scenarioAllocationFromDailyRows(rows, topN, maxWeight) {
  const scoreRows = rows.map((row) => ({
    symbol: row.symbol,
    score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.actualWeight) || 0,
  }));
  return computeScenarioAllocation(scoreRows, topN, maxWeight);
}

function selectedDailyWeightRows(run, date, windowKey, factor, topN, maxWeight) {
  const exactSnapshot = factorWeightSnapshot(run, date, windowKey, factor);
  const snapshotCandidates = (run.factor_weight_snapshots || [])
    .filter((snapshot) => snapshot.factor === factor && snapshot.window === windowKey && String(snapshot.date || '') <= String(date || '9999-99-99'))
    .sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  const snapshot = exactSnapshot || snapshotCandidates[0] || null;
  const historyRows = (run.holdings || [])
    .filter((row) => row.factor === factor && row.window === windowKey && String(row.date || '') <= String(date || '9999-99-99'));
  const historyDates = [...new Set(historyRows.map((row) => row.date).filter(Boolean))]
    .sort((a, b) => String(b).localeCompare(String(a)))
    .slice(0, 5);
  const groupedRows = [];
  historyDates.forEach((day) => {
    const rowsForDay = normalizeDailyActualRows(historyRows.filter((row) => row.date === day))
      .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
      .slice(0, topN);
    const allocation = scenarioAllocationFromDailyRows(rowsForDay, topN, maxWeight);
    const scenarioBySymbol = new Map((allocation.weighted || []).map((row) => [String(row.symbol), row]));
    rowsForDay.forEach((row) => {
      const scenarioWeight = Number(scenarioBySymbol.get(String(row.symbol))?.display_weight) || 0;
      groupedRows.push({
        ...row,
        scenarioWeight,
        deltaWeight: scenarioWeight - row.actualWeight,
        scenarioSource: 'daily_holding_score_reweight',
      });
    });
  });

  if (groupedRows.length) {
    return {
      rows: groupedRows,
      sourceKind: 'historical_holdings',
      snapshot,
      dateCount: historyDates.length,
      exactDate: historyDates.includes(date),
    };
  }

  if (snapshot) {
    const rowsForSnapshot = normalizeDailyActualRows(snapshot.rows || [], snapshot)
      .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
      .slice(0, topN);
    const allocation = scenarioAllocationFromDailyRows(rowsForSnapshot, topN, maxWeight);
    const scenarioBySymbol = new Map((allocation.weighted || []).map((row) => [String(row.symbol), row]));
    return {
      rows: rowsForSnapshot.map((row) => {
        const scenarioWeight = Number(scenarioBySymbol.get(String(row.symbol))?.display_weight) || 0;
        return {
          ...row,
          scenarioWeight,
          deltaWeight: scenarioWeight - row.actualWeight,
          scenarioSource: 'factor_weight_snapshot_reweight',
        };
      }),
      sourceKind: exactSnapshot ? 'exact_weight_snapshot' : 'nearest_weight_snapshot',
      snapshot,
      dateCount: 1,
      exactDate: Boolean(exactSnapshot),
    };
  }

  const scenario = currentWeightedHoldings();
  return {
    rows: (scenario.weighted || []).slice(0, topN).map((row, index) => ({
      date,
      window: windowKey,
      windowLabel: scenario.windowLabel,
      factor,
      rank: row.display_rank || index + 1,
      symbol: row.symbol,
      actualWeight: null,
      scenarioWeight: Number(row.display_weight) || 0,
      deltaWeight: null,
      score: row.score,
      weightDate: date,
      scoreDate: scenario.scoreDate || date,
      source: scenario.scoreScope || '점수 스냅샷 기반 시나리오',
      scenarioSource: 'score_snapshot_only',
    })),
    sourceKind: 'score_snapshot_only',
    snapshot: null,
    dateCount: 1,
    exactDate: false,
  };
}

function renderDailyWeightsAnalysis() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  const topN = params.topN;
  const maxWeight = params.maxWeight;
  const { rows, sourceKind, snapshot, dateCount, exactDate } = selectedDailyWeightRows(run, date, windowKey, factor, topN, maxWeight);

  setText(
    '#daily-weight-analysis-note',
    sourceKind === 'historical_holdings'
      ? `${date || '-'} 이하 최근 ${dateCount}개 보유일의 선택 팩터 ${factor || '-'} 비중입니다. 종목을 열로 배치해 날짜별 저장 비중과 현재 입력 시나리오 비중을 바로 비교합니다.`
      : snapshot
      ? `${snapshot.date || date || '-'} 기준 선택 팩터 ${factor || '-'}의 ${exactDate ? '정확한' : '가장 가까운'} 보유 비중 스냅샷입니다. 종목 열마다 저장/현재 입력 비중을 함께 표시합니다.`
      : `${date || '-'} 기준 선택 팩터 ${factor || '-'}의 저장 보유 비중이 없어 점수 스냅샷 기반 시나리오 비중만 종목별로 표시합니다.`,
  );

  const table = document.querySelector('#daily-weights-table');
  const thead = table?.querySelector('thead');
  const tbody = table?.querySelector('tbody');
  if (!table || !thead || !tbody) return;

  tbody.replaceChildren();
  const symbols = [...new Set(rows.map((row) => row.symbol).filter(Boolean))].slice(0, Math.max(1, Math.min(topN, 24)));
  const headerRow = document.createElement('tr');
  appendHeaderCell(headerRow, '비중일');
  appendHeaderCell(headerRow, '기간');
  symbols.forEach((symbol) => appendHeaderCell(headerRow, symbol));
  thead.replaceChildren(headerRow);

  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = Math.max(symbols.length + 2, 3);
    td.textContent = '선택한 기준일과 팩터에 표시할 일별 투자 비중 데이터가 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const groups = new Map();
  rows.forEach((row) => {
    const key = `${row.weightDate || row.date || '-'}|${row.windowLabel || row.window || '-'}`;
    if (!groups.has(key)) {
      groups.set(key, {
        date: row.weightDate || row.date || '-',
        windowLabel: row.windowLabel || row.window || '-',
        bySymbol: new Map(),
      });
    }
    if (row.symbol) groups.get(key).bySymbol.set(row.symbol, row);
  });

  [...groups.values()]
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .forEach((group) => {
      const tr = document.createElement('tr');
      appendCell(tr, group.date);
      appendCell(tr, group.windowLabel);
      symbols.forEach((symbol) => appendWeightMatrixCell(tr, group.bySymbol.get(symbol)));
      tbody.appendChild(tr);
    });
}

function appendHeaderCell(tr, text) {
  const th = document.createElement('th');
  th.scope = 'col';
  th.textContent = text;
  tr.appendChild(th);
}

function appendWeightMatrixCell(tr, row) {
  const td = document.createElement('td');
  td.className = 'weight-matrix-cell';
  if (!row) {
    td.textContent = '-';
    tr.appendChild(td);
    return;
  }
  const primary = document.createElement('strong');
  primary.textContent = row.actualWeight === null ? formatPercent(row.scenarioWeight) : formatPercent(row.actualWeight);
  const secondary = document.createElement('small');
  const parts = [];
  if (row.actualWeight !== null) parts.push(`현재 ${formatPercent(row.scenarioWeight)}`);
  if (row.deltaWeight !== null) parts.push(`차이 ${formatPercent(row.deltaWeight)}`);
  if (Number.isFinite(Number(row.score))) parts.push(`신호 ${formatNumber(row.score)}`);
  secondary.textContent = parts.join(' · ') || '시나리오 비중';
  td.title = `${row.symbol || ''} ${row.scoreDate ? `신호일 ${row.scoreDate}` : ''}`.trim();
  td.append(primary, secondary);
  tr.appendChild(td);
}

function parseSelectedFactorMethod(factor, option = {}) {
  const text = String(factor || '');
  const override = FACTOR_METHOD_OVERRIDES[text] || null;
  const category = humanFactorCategory(override?.category || option.category || 'unknown');
  const base = {
    category,
    formulaLabel: override?.formula || '팩터별 가격/거래량·재무 신호 산식',
    lookback: '팩터명 또는 카탈로그 정의 구간',
    skip: '팩터별 정의에 따름',
    score: override
      ? `${text} 원자료 산식은 ${override.formula}입니다. 각 종목에 같은 산식을 적용한 뒤 점수가 높은 순서로 후보를 정렬합니다.`
      : '종목별 가격 기반 신호를 계산한 뒤 값이 큰 순서로 순위를 매깁니다.',
    caveat: override
      ? `${override.description} 검증 메모: ${override.validation}`
      : option.description_ko || option.description || '세부 설명 정보가 제한적이므로 팩터명과 카테고리 기반으로 해석합니다.',
  };
  let match = text.match(/^mom_(\d+)_(\d+)$/);
  if (match) {
    const lookback = Number(match[1]);
    const skip = Number(match[2]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t-${skip}m) / P_i(t-${lookback + skip}m) - 1`,
      lookback: `최근 ${skip}개월을 제외한 직전 ${lookback}개월 가격 변화`,
      skip: `${skip}개월 스킵/제외`,
      score: `각 종목 i에 대해 최근 ${skip}개월을 제외한 직전 ${lookback}개월 누적수익률을 계산합니다. 즉 대략 P_i(t-${skip}m) / P_i(t-${lookback + skip}m) - 1이며, 값이 큰 종목이 상위 모멘텀 후보입니다.`,
      caveat: `${base.caveat} 최근 과열/단기 반전 오염을 줄이기 위해 가장 최근 ${skip}개월은 점수 계산 구간에서 제외합니다.`,
    };
  }
  match = text.match(/^mom_(\d+)m$/);
  if (match) {
    const lookback = Number(match[1]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / P_i(t-${lookback}m) - 1`,
      lookback: `${lookback}개월 가격 변화`,
      skip: '명시적 스킵 없음',
      score: `각 종목의 최근 ${lookback}개월 누적수익률을 계산하고 높은 순서로 정렬합니다. 원자료 산식은 조정종가 기준 가격 변화율입니다.`,
      caveat: `${base.caveat} 단순 기간 모멘텀은 빠른 추세를 직접 보지만 단기 과열과 회전율에 더 민감할 수 있습니다.`,
    };
  }
  match = text.match(/^mom_(\d+)d$/);
  if (match) {
    const days = Number(match[1]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / P_i(t-${days}d) - 1`,
      lookback: `${days}거래일`,
      skip: '명시적 스킵 없음',
      score: `최근 ${days}거래일 내외의 단기 가격 변화를 비교해 단기 모멘텀이 강한 종목을 위로 정렬합니다.`,
      caveat: `${base.caveat} 단기 모멘텀 팩터는 회전율과 반전 위험이 커서 비용/슬리피지 민감도를 함께 봐야 합니다.`,
    };
  }
  match = text.match(/^accel_(\d+)m_vs_(\d+)m$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `${match[1]}개월 모멘텀 - ${match[2]}개월 모멘텀`,
      lookback: `${match[1]}개월과 ${match[2]}개월 수익률 비교`,
      skip: '팩터 정의의 skip 값 적용',
      score: `짧은 기간 모멘텀이 긴 기간 모멘텀보다 얼마나 개선됐는지 계산합니다. 값이 클수록 최근 리더십이 가속된 종목입니다.`,
      caveat: `${base.caveat} 가속도 계열은 추세 변화 속도를 보므로 단순 장기 모멘텀보다 노이즈에 민감할 수 있습니다.`,
    };
  }
  match = text.match(/^high_(\d+)w$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / rolling_high_${match[1]}w - 1`,
      lookback: `${match[1]}주 고점/현재가 비교`,
      skip: '명시적 스킵 없음',
      score: `현재 가격이 ${match[1]}주 고점에 얼마나 가까운지로 추세 지속성을 평가합니다. 0에 가까울수록 고점 근접도가 높습니다.`,
      caveat: `${base.caveat} 고점 근접 팩터는 강한 추세를 빠르게 포착하지만 추세 말기 변동성에 유의해야 합니다.`,
    };
  }
  match = text.match(/^breakout_(\d+)d$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / prior_high_${match[1]}d - 1 + 확인 모멘텀`,
      lookback: `${match[1]}거래일 가격 범위`,
      skip: '명시적 스킵 없음',
      score: `최근 ${match[1]}거래일 가격 범위에서 상단 돌파/근접 정도와 확인 모멘텀을 함께 평가합니다.`,
      caveat: `${base.caveat} 돌파 팩터는 추세 시작을 포착하려 하지만 false breakout과 비용 민감도가 있습니다.`,
    };
  }
  if (text.includes('winsorized') || text.includes('gap_resistant') || text.includes('jump_excluded') || text.includes('median_return')) {
    return {
      ...base,
      lookback: '주로 63~252거래일 견고화 구간',
      score: `${base.score} 급등락·단일 점프·극단 일수익률 영향을 줄이는 견고화 처리를 포함합니다.`,
      caveat: `${base.caveat} 견고화 계열은 한두 번의 급등락에 덜 끌려가지만, 실제 급격한 추세 전환을 일부 늦게 반영할 수 있습니다.`,
    };
  }
  if (text.includes('risk') || text.includes('vol') || text.includes('ulcer') || text.includes('drawdown') || text.includes('tail')) {
    return {
      ...base,
      lookback: '모멘텀 구간과 63~252거래일 위험 구간',
      score: `${base.score} 상승률을 변동성, 낙폭, 하방위험, 좌측 꼬리위험 같은 위험 지표로 보정합니다.`,
      caveat: `${base.caveat} 위험조정 계열은 단순 수익률보다 안정성을 선호하지만 강한 고변동 추세를 낮게 볼 수 있습니다.`,
    };
  }
  if (text.includes('ma_') || text.includes('trend') || text.includes('range_position') || text.includes('price_vs_ma')) {
    return {
      ...base,
      lookback: '20~252거래일 추세·이동평균·가격 범위 구간',
      score: `${base.score} 이동평균 기울기, 추세 정렬, 가격 범위 내 위치 등을 이용해 추세 품질을 평가합니다.`,
      caveat: `${base.caveat} 추세 품질 계열은 방향성과 지속성을 함께 보지만 횡보장에서는 신호가 둔화될 수 있습니다.`,
    };
  }
  if (text.includes('relative_strength') || text.includes('residual') || text.includes('excess_ir') || text.includes('up_down_capture')) {
    return {
      ...base,
      lookback: '주로 126~252거래일 횡단면/시장상대 구간',
      score: `${base.score} 동일 후보군 또는 시장 프록시 대비 초과 성과·상대 순위·상승/하락 참여도를 비교합니다.`,
      caveat: `${base.caveat} 상대강도 계열은 후보군 구성과 시장 프록시 변화에 민감하므로 단독 투자 결론보다 비교 진단으로 보세요.`,
    };
  }
  return base;
}

function appendMethodItem(target, label, value) {
  const item = document.createElement('div');
  item.className = 'method-item';
  const strong = document.createElement('strong');
  strong.textContent = label;
  const small = document.createElement('small');
  small.textContent = textValue(value);
  item.append(strong, small);
  target.appendChild(item);
}

function renderSelectedFactorMethod() {
  const run = currentRun();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  const option = factorOptions(run).find((item) => item.factor === factor) || {};
  const method = parseSelectedFactorMethod(factor, option);
  setText('#selected-factor-method-title', factor || '-');
  setText('#selected-factor-method-badge', `${method.category} · 브라우저 시나리오 설명`);
  setText(
    '#selected-factor-method-summary',
    `${factor || '-'} 계산법: ${method.score} 현재 화면의 비중/성과 비교는 이 점수 순위를 기반으로 최근 ${params.lookbackMonths}개월, 상위 ${params.topN}개, 종목당 최대 ${formatPercent(params.maxWeight)}, ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 리밸런싱, 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps 가정을 적용한 브라우저 시나리오/민감도 프록시입니다.`,
  );
  const steps = document.querySelector('#selected-factor-method-steps');
  if (steps) {
    steps.replaceChildren();
    appendMethodItem(steps, '팩터 분류', method.category);
    appendMethodItem(steps, '핵심 산식', method.formulaLabel);
    appendMethodItem(steps, '관찰 구간', method.lookback);
    appendMethodItem(steps, '최근 구간 제외', method.skip);
    appendMethodItem(steps, '비중 적용', `점수 상위 ${params.topN}개를 점수 비례로 배분하고 종목당 ${formatPercent(params.maxWeight)} 상한을 적용합니다.`);
    appendMethodItem(steps, '성과 적용', `저장된 팩터 누적성과를 비중 집중도와 ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 비용 프록시로 조정합니다.`);
  }
  setText(
    '#selected-factor-method-note',
    `${method.caveat} 이 페이지는 서버에서 전체 일별 구성종목을 재백테스트한 결과가 아니라, 저장된 점수/비중 스냅샷과 팩터 누적성과를 현재 입력값으로 다시 해석한 브라우저 시나리오/프록시입니다.`,
  );
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  let rows = scenarioPeriodRows(run, date, windowKey, params);
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 40);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, `${row.window_label || windowKey} · 시나리오`);
    appendCell(tr, row.factor, { strong: row.factor === factor });
    appendCell(tr, `${formatPercent(row.period_return)}${row.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(row.raw_period_return)}` : ''}`, { className: classForNumber(row.period_return) });
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
  if (!state.data) return;
  renderSummary();
  renderDiagnostics();
  renderSelectedFactorMethod();
  renderFactorReturnChart();
  renderBacktestChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
  renderEnsembleWeightChart();
  renderCurrentOutputTable();
  renderFactorTable();
  renderHoldingsTable();
  renderDailyWeightsAnalysis();
  renderPeriodRankingTable();
}

function renderWithBusy(message = '선택값을 반영하는 중입니다...') {
  if (!state.data) {
    setStatusMessage('데이터를 불러오는 중입니다. 입력값은 데이터 로딩 후 반영됩니다.');
    return;
  }
  setStatusMessage(message);
  window.setTimeout(() => {
    renderAll();
  }, 160);
}

bindManualUpdateControls();

if (typeof document.querySelectorAll === 'function') {
  document.querySelectorAll('[data-topn-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.querySelector('#topn-input');
      if (input) input.value = button.getAttribute('data-topn-preset') || DASHBOARD_INPUT_DEFAULTS.topN;
      renderWithBusy('상위 종목 수 프리셋을 반영하는 중입니다...');
    });
  });
  document.querySelectorAll('[data-max-weight-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.querySelector('#max-weight-input');
      if (input) input.value = button.getAttribute('data-max-weight-preset') || DASHBOARD_INPUT_DEFAULTS.maxWeightPercent;
      renderWithBusy('최대 비중 프리셋을 반영하는 중입니다...');
    });
  });
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
      state.hasUserSelectedFactor = false;
      fillControls();
      renderWithBusy('실행 결과를 전환하는 중입니다...');
    });
    document.querySelector('#factor-select').addEventListener('change', () => {
      state.hasUserSelectedFactor = true;
      fillDateOptions(currentRun(), selectedDate());
      renderWithBusy('선택 팩터를 반영하는 중입니다...');
    });
    ['#date-select', '#window-select'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => {
        syncDefaultFactorToCurrentBasis();
        renderWithBusy('기준일·기간의 최고 팩터를 반영하는 중입니다...');
      });
      document.querySelector(selector).addEventListener('change', () => {
        syncDefaultFactorToCurrentBasis();
        renderWithBusy('기준일·기간의 최고 팩터를 반영하는 중입니다...');
      });
    });
    ['#lookback-months-select', '#topn-input', '#max-weight-input', '#rebalance-select', '#transaction-cost-input', '#slippage-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => renderWithBusy('선택값을 반영하는 중입니다...'));
      document.querySelector(selector).addEventListener('change', () => renderWithBusy('선택값을 반영하는 중입니다...'));
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
