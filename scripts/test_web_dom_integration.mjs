import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");
const js = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");

const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
const requiredHosts = [
  "run-status",
  "best-factor",
  "selected-factor",
  "recommendation-status",
  "data-quality-summary",
  "tradability-gate-list",
  "selected-factor-method-title",
  "factor-category-summary",
  "factor-rank-ic-summary",
  "factor-redundancy-summary",
  "factor-return-chart",
  "backtest-chart",
  "performance-metrics-table",
  "window-comparison-chart",
  "leader-trend-chart",
  "weight-chart",
  "factor-table",
  "holdings-table",
  "daily-weights-table",
  "period-ranking-table",
  "joint-ranking-chart",
  "joint-ranking-table",
  "joint-ranking-scope",
  "joint-ranking-title",
  "joint-ranking-scope-note",
  "canonical-component-chart",
  "canonical-policy-cards",
  "canonical-guardrail-list",
  "canonical-data-contract",
  "canonical-universe-scope",
  "canonical-universe-evidence",
];
for (const id of requiredHosts) assert(ids.has(id), `missing live-render host: ${id}`);

const literalSelectors = [
  ...js.matchAll(/(?:querySelector|setText|appendEmpty)\(['"]#([A-Za-z0-9_-]+)/g),
].map((match) => match[1]);
const missingSelectors = [...new Set(literalSelectors)].filter((id) => !ids.has(id));
assert.deepEqual(missingSelectors, [], "every literal id selector must resolve in the restored HTML");

assert.match(js, /renderAll\(\)[\s\S]*renderFactorReturnChart\(\);[\s\S]*renderBacktestChart\(\);/);
assert.match(js, /renderAll\(\)[\s\S]*renderWindowComparisonChart\(\);[\s\S]*renderLeaderTrendChart\(\);/);
assert.match(js, /renderAll\(\)[\s\S]*renderWeightChart\(\);[\s\S]*renderFactorTable\(\);/);
assert.match(js, /renderAll\(\)[\s\S]*renderCanonicalResearch\(\);/);
assert.match(js, /benchmarkSeriesList\.forEach/);
assert.match(js, /renderPythonPerformanceMetricsTable/);
assert.match(js, /series\.symbol !== '\^IXIC'/);
assert.match(js, /commonPeriod \? '전체 공통 평가기간' : '최근 백테스트'/);
assert.match(js, /selectedBacktestHoldingHistory/);
assert.match(js, /\.slice\(0, 21\)/);
assert.doesNotMatch(js, /historyDates[\s\S]{0,180}\.slice\(0, 5\)/);
assert.match(js, /aria-pressed/);
assert.match(js, /const CHART_PALETTE_CLASS_MAP = Object\.freeze/);
assert.match(js, /canonicalSelectionStatusClass\(row\.selection_status\)/);
assert.match(js, /CHART_PALETTE_CLASS_MAP\.bars\.focal/);
assert.match(js, /benchmarkPaletteClass\(series\.symbol\)/);
assert.match(
  js,
  /const best = periodBestStats\(run, date, windowKey\);/,
  "the Python chart's best factor must come directly from the Python period matrix",
);
const renderBacktestChartSource = js.match(/function renderBacktestChart\(\) \{[\s\S]*?\n\}\n\nfunction pythonPerformanceSource/)?.[0] || "";
assert.doesNotMatch(renderBacktestChartSource, /scenarioBestStats|scenarioAdjusted|inputScenarioParameters/);
assert.match(renderBacktestChartSource, /브라우저 추정값으로 대체하지 않습니다/);
assert.doesNotMatch(js, /fresh_price_ratio:\s*1/);
assert.match(js, /freshCandidateRows\.length \/ candidateQualityRows\.length/);
assert.match(js, /score_scope: 'schema_v4_current_python_portfolio_top_constituents'/);
assert.match(js, /capacity_status_counts: null/);
assert.match(js, /function formatSourceHealth\(rows, context = \{\}\)/);
assert.doesNotMatch(js, /\.filter\(\(row\) => row && row\.source\)\s*\.slice\(0, 8\)/);
assert.match(js, /function canonicalGridAccounting\(payload\)/);
assert.match(js, /accounting\.availableIndependentPairCount/);
assert.match(js, /accounting\.excludedIndependentPairCount/);
assert.match(js, /accounting\.commonComparableFactorCount/);
assert.match(js, /accounting\.diagnosticAliasPairCount/);
assert.match(js, /canonicalRankingStatusText\(row\)/);
assert.doesNotMatch(js, /appendCell\(tr, row\.selected === true \? '선택' : row\.selection_status/);
assert.match(js, /terminal_nav_unavailable: '최종 NAV 평가 불가\(선정 제외·진단용\)'/);
assert.match(js, /이미 보유 중 발생한 극단 움직임은 발생 이후 전략 수익률에 인과적으로 반영/);
assert.match(js, /최종 NAV가 없는 조합은 수익률 크기와 무관하게 선정에서 제외하고 진단용으로만 남깁니다/);
assert.match(js, /동일 표본 상대 합성 점수/);
assert.match(js, /절대 신뢰도나 미래 성공 확률이 아닙니다/);
assert.match(js, /rows\.filter\(\(row\) => finite\(row\.selection_score\)\)/);
assert.match(
  js,
  /function canonicalSelectFactor\(factor\)[\s\S]*syncFactorDependentControls\(currentRun\(\), factor, preferredDate\);[\s\S]*renderAll\(\);/,
  "joint-ranking clicks must synchronize factor-dependent date and Top-N controls before rendering",
);

assert.match(
  html,
  /아래 값이 공식 결과의 입력입니다/,
);
assert.match(
  html,
  /성과 탐색 기간은 비교선만 정하며, 공식 선택은 입력 폼의 평가기간/,
);
assert.doesNotMatch(html, /id="(?:topn-input|max-weight-input|lookback-months-select)"/);
assert.doesNotMatch(html, /현재 canonical 목표/);
assert.match(html, /id="input-top-n"[^>]*max="50"/);
assert.match(html, /이 조건으로 Python 분석/);
assert.match(html, /데이터 품질 · 최종 편입 적격 · 매매 가능성 게이트/);
assert.doesNotMatch(html, /유동성 적격 종목/);
assert.match(html, /동일 표본 상대 점수/);
assert.match(html, /동일 표본 상대 percentile · 절대 신뢰도 아님/);
assert.match(html, /유니버스 시점성 · 생존편향 한계/);
assert.match(
  html,
  /<a class="skip-link" href="#main-content">본문으로 건너뛰기<\/a>/,
  "the visible-on-focus skip link must target the dashboard main content",
);
assert.match(html, /<main id="main-content" tabindex="-1">/);

const manualUpdateIndex = html.indexOf('class="manual-update"');
const guardrailIndex = html.indexOf('id="canonical-guardrail-list"');
const dataQualityIndex = html.indexOf('id="data-quality-summary"');
assert(manualUpdateIndex >= 0 && guardrailIndex > manualUpdateIndex, "absolute guardrails must follow manual update");
assert(dataQualityIndex > guardrailIndex, "data-quality/tradability gates must follow the absolute guardrails");

assert.match(css, /\.canonical-bar-row\s*\{/);
assert.match(css, /\.canonical-bar-row\.is-selected/);
assert.match(css, /\.policy-equal-weight/);
assert.match(css, /\.policy-capped-linear-rank/);
assert.match(css, /\.policy-capped-vol-adjusted-rank/);
assert.match(css, /\.policy-score-liquidity-rank/);
assert.match(css, /\.canonical-bar-row\.status-data-excluded/);
assert.match(css, /\.canonical-bar-row\.status-extreme-event-excluded/);
assert.match(css, /\.canonical-bar-row\.chart-bar-focal \.bar-fill/);
assert.match(css, /\.component-chart \.canonical-bar-row\.chart-bar-component \.bar-fill/);
assert.match(css, /\.line-path\.selected/);
assert.match(css, /\.line-path\.best/);
assert.match(css, /\.line-path\.benchmark-spy/);
assert.match(css, /\.line-path\.benchmark-ixic/);
assert.match(css, /\.line-path\.benchmark-qqq/);
assert.match(css, /@media \(max-width: 720px\)[\s\S]*\.canonical-bar-row/);
assert.match(css, /\.performance-table\s*\{[\s\S]*min-width:\s*560px/);
assert.match(css, /\.performance-table-wrap\s*\{[\s\S]*overflow-x:\s*auto/);
assert.match(css, /\.daily-weights-scroll\s*\{[\s\S]*max-height:\s*560px;[\s\S]*overflow:\s*auto/);
assert.match(html, /종목별 백테스트 보유 \/ 현재 Python 포트폴리오/);
assert.match(
  html,
  /class="table-wrap daily-weights-scroll"[\s\S]*role="region"[\s\S]*tabindex="0"[\s\S]*aria-label="비교 팩터 실제 백테스트 보유와 현재 Python 포트폴리오 비교표"[\s\S]*aria-describedby="daily-weight-analysis-note"/,
);
assert.match(
  html,
  /<table id="daily-weights-table" aria-describedby="daily-weight-analysis-note">[\s\S]*<caption class="visually-hidden">[^<]*최근 최대 21개[^<]*<\/caption>/,
  "the wide daily-weight table needs a nonvisual caption and the live explanatory note",
);
assert.match(
  html,
  /<th scope="col">보유 기준일<\/th>[\s\S]*<th scope="col">신호일 · 체결일<\/th>/,
);
assert.match(js, /wrap\.setAttribute\('role', 'region'\)/);
assert.match(js, /wrap\.setAttribute\('tabindex', '0'\)/);
assert.match(js, /aria-describedby', 'python-performance-metrics-note'/);
assert.match(css, /\.performance-table tbody th\[scope="row"\]/);

console.log("PASS restored DOM hosts, render wiring, accessible states, palette, and responsive contracts");
