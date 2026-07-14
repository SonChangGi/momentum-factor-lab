import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const previewPayloadPath = process.env.MFL_TEST_PAYLOAD || (
  existsSync("outputs/final-evidence-preview-20260713/site/data/dashboard.json")
    ? "outputs/final-evidence-preview-20260713/site/data/dashboard.json"
    : existsSync("outputs/daily-dashboard-reality-preview/site/data/dashboard.json")
      ? "outputs/daily-dashboard-reality-preview/site/data/dashboard.json"
      : "outputs/daily-dashboard/default-detail.json"
);
const publishedPayloadPath = "docs/data/dashboard.json";
const payloadPath = existsSync(previewPayloadPath) ? previewPayloadPath : publishedPayloadPath;
const payload = JSON.parse(readFileSync(payloadPath, "utf8"));

const context = vm.createContext({
  console,
  setTimeout,
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
  crypto: webcrypto,
});
vm.runInContext(source, context, { filename: "momentum_factor_lab/web/dashboard.js" });
const api = context.__MFL_WEB_TESTS__;
assert(api, "web helper API must be exported without requiring a DOM");
const clonePayload = (value) => JSON.parse(JSON.stringify(value));

assert.equal(payload.schemaVersion, 4);
assert.equal(payload.data.mode, "live_market");
assert.equal(payload.data.synthetic, false);
assert(payload.data.analyzedSecurityCount >= 2700);
assert.equal(payload.factorPolicyRanking.length, 256);
assert.equal(payload.gridAccounting.independentFactorCount, 61);
assert.equal(payload.gridAccounting.diagnosticAliasFactorCount, 3);
const gridAccounting = api.canonicalGridAccounting(payload);
assert.equal(gridAccounting.expectedIndependentPairCount, 244);
assert.equal(gridAccounting.evaluatedIndependentPairCount, 244);
const independentFactors = new Set(
  payload.factorDefinitions
    .filter((row) => !row.compatibility_alias_of)
    .map((row) => row.factor),
);
const independentPairRows = payload.factorPolicyRanking.filter((row) => (
  independentFactors.has(row.factor)
));
const derivedAvailableIndependentPairCount = independentPairRows.filter((row) => (
  row.comparison_status === "available"
)).length;
const derivedExcludedIndependentPairCount = independentPairRows.length
  - derivedAvailableIndependentPairCount;
const derivedCommonComparableFactorCount = [...independentFactors].filter((factor) => (
  independentPairRows.filter((row) => (
    row.factor === factor && row.comparison_status === "available"
  )).length === gridAccounting.policyCount
)).length;
assert.equal(
  gridAccounting.availableIndependentPairCount,
  derivedAvailableIndependentPairCount,
  "available pair accounting must be derived from this preset's comparison rows",
);
assert.equal(
  gridAccounting.excludedIndependentPairCount,
  derivedExcludedIndependentPairCount,
  "excluded pair accounting must be derived from this preset's comparison rows",
);
assert.equal(
  gridAccounting.commonComparableFactorCount,
  derivedCommonComparableFactorCount,
  "common-comparable factor count must work for every top-N/date preset",
);
assert.equal(gridAccounting.diagnosticAliasPairCount, 12);
assert.equal(gridAccounting.totalOutputRowCount, 256);
assert.equal(
  gridAccounting.availableIndependentPairCount + gridAccounting.excludedIndependentPairCount,
  gridAccounting.expectedIndependentPairCount,
  "available and excluded independent pairs must account for the complete 244-pair grid",
);
assert.equal(
  gridAccounting.commonComparableFactorCount * gridAccounting.policyCount,
  gridAccounting.availableIndependentPairCount,
  "only common-comparable factors across four policies may receive a relative rank",
);

const syntheticAccounting = api.canonicalGridAccounting({
  gridAccounting: {
    independentFactorCount: 7,
    policyCount: 3,
    expectedIndependentPairCount: 21,
    evaluatedIndependentPairCount: 20,
    availableIndependentPairCount: 9,
    excludedIndependentPairCount: 11,
    commonComparableFactorCount: 3,
    diagnosticAliasFactorCount: 2,
    diagnosticAliasPairCount: 6,
    missingIndependentPairCount: 1,
  },
  factorPolicyRanking: Array.from({ length: 26 }, (_, index) => ({ index })),
});
assert.equal(syntheticAccounting.expectedIndependentPairCount, 21);
assert.equal(syntheticAccounting.availableIndependentPairCount, 9);
assert.equal(syntheticAccounting.excludedIndependentPairCount, 11);
assert.equal(syntheticAccounting.commonComparableFactorCount, 3);
assert.equal(syntheticAccounting.diagnosticAliasPairCount, 6);
assert.equal(syntheticAccounting.totalOutputRowCount, 26, "grid copy must derive from payload values, not hard-coded 256/244 counts");

const terminalNavExcluded = payload.factorPolicyRanking.find((row) => (
  row.selection_status === "data_excluded"
  && row.exclusion_reason_codes?.includes("terminal_nav_unavailable")
));
assert(terminalNavExcluded, "actual grid must retain terminal-NAV exclusions for diagnostics");
const terminalStatusText = api.canonicalRankingStatusText(terminalNavExcluded);
assert.match(terminalStatusText, /데이터 조건 미충족/);
assert.match(terminalStatusText, /최종 NAV 평가 불가\(선정 제외·진단용\)/);
assert.doesNotMatch(terminalStatusText, /data_excluded|terminal_nav_unavailable/);
const aliasExcluded = payload.factorPolicyRanking.find((row) => row.exclusion_reason_codes?.includes("duplicate_alias"));
assert(aliasExcluded, "actual grid must retain compatibility aliases as separate diagnostics");
const aliasStatusText = api.canonicalRankingStatusText(aliasExcluded);
assert.match(aliasStatusText, /독립 팩터와 중복된 호환 alias/);
assert.doesNotMatch(aliasStatusText, /data_excluded|duplicate_alias/);

const partialRiskRow = payload.factorPolicyRanking.find((row) => (
  row.comparison_status === "available" && row.risk_metrics_exact === false
));
assert(partialRiskRow, "actual grid must expose at least one available partial-risk row");
const partialRiskText = api.canonicalRiskQualityText(partialRiskRow);
assert.match(partialRiskText, /불완전/);
assert.match(partialRiskText, /일간 위험/);
assert.match(partialRiskText, /quote gap/);
assert.match(partialRiskText, /평가/);
assert.match(partialRiskText, /MDD는 관측 종가 기준 하한/);
const exactRiskRow = payload.factorPolicyRanking.find((row) => row.risk_metrics_exact === true);
assert(exactRiskRow, "actual grid must expose at least one exact-risk row");
assert.match(api.canonicalRiskQualityText(exactRiskRow), /^exact/);

assert.match(api.canonicalScoreMethodDescription({
  config: {
    score_winsor_lower: 0.10,
    score_winsor_upper: 0.90,
    stability_periods: 5,
  },
}), /10%~90%.*5개 하위기간/);

const benchmarkCurves = payload.performance.benchmarkCurves;
assert(benchmarkCurves && typeof benchmarkCurves === "object", "Python payload must expose benchmarkCurves");
assert.deepEqual(
  Array.from(payload.performance.benchmarkOrder),
  ["SPY", "^IXIC", "QQQ"],
  "benchmarkOrder must preserve SPY, the original Nasdaq comparator, then QQQ",
);
assert.deepEqual(
  Object.keys(benchmarkCurves).sort(),
  ["QQQ", "SPY", "^IXIC"],
  "canonical JSON key sorting must not change the benchmark set",
);
for (const symbol of ["SPY", "^IXIC", "QQQ"]) {
  assert.equal(
    benchmarkCurves[symbol].length,
    payload.performance.dates.length,
    `${symbol} must share the selected-policy comparison dates`,
  );
  assert(!payload.data.analyzedSymbols.includes(symbol), `${symbol} must never enter holdings candidates`);
}

assert.deepEqual(
  payload.performance.periods.map((period) => period.key),
  ["1W", "1M", "3M", "6M", "1Y", "YTD", "FULL"],
);
for (const period of payload.performance.periods) {
  assert.equal(period.endDate, payload.data.asOf);
  assert(period.factors[payload.selectedFactor], `${period.key} must contain the selected factor`);
  for (const symbol of ["SPY", "^IXIC", "QQQ"]) {
    assert(period.benchmarks[symbol], `${period.key} must contain ${symbol}`);
  }
}
const oneMonth = payload.performance.periods.find((period) => period.key === "1M");
assert.equal(oneMonth.returnObservationCount, 21);
assert.equal(api.validatePerformance(payload), payload.performance);
assert.equal(api.validateBacktestHeldPortfolio(payload), payload.backtestHeldPortfolio);
assert.equal(
  api.validateSelectedBacktestHoldingHistory(payload, payload.backtestHeldPortfolio),
  payload.selectedBacktestHoldingHistory,
);
assert.equal(
  api.validateFactorHoldingHistorySidecarManifest(payload),
  payload.factorHoldingHistorySidecar,
);

const mismatchedBenchmarkEndpoint = clonePayload(payload);
mismatchedBenchmarkEndpoint.performance.benchmarkCurves.QQQ[
  mismatchedBenchmarkEndpoint.performance.benchmarkCurves.QQQ.length - 1
] *= 0.5;
assert.throws(
  () => api.validatePerformance(mismatchedBenchmarkEndpoint),
  /QQQ FULL 누적 수익률이 그래프 endpoint와 다릅니다/,
);
const malformedCurve = clonePayload(payload);
malformedCurve.performance.factorCurves[payload.selectedFactor][0] = "bad";
assert.throws(
  () => api.validatePerformance(malformedCurve),
  /길이\/유한값\/null gap/,
);
const factorCurveWithExplicitGap = clonePayload(payload);
factorCurveWithExplicitGap.performance.factorCurves[payload.selectedFactor][1] = null;
assert.equal(api.validatePerformance(factorCurveWithExplicitGap), factorCurveWithExplicitGap.performance);

for (const field of [
  "backtestHeldPortfolio",
  "selectedBacktestHoldingHistory",
  "factorHoldingHistorySidecar",
]) {
  const missing = clonePayload(payload);
  delete missing[field];
  assert.throws(
    () => {
      if (field === "backtestHeldPortfolio") api.validateBacktestHeldPortfolio(missing);
      else if (field === "selectedBacktestHoldingHistory") {
        api.validateSelectedBacktestHoldingHistory(missing, missing.backtestHeldPortfolio);
      } else api.validateFactorHoldingHistorySidecarManifest(missing);
    },
    /backtestHeldPortfolio|selectedBacktestHoldingHistory|sidecar manifest/,
  );
}
for (const key of [
  "cumulativeReturn",
  "sharpe",
  "annualizedVolatility",
  "maxDrawdown",
  "sortino",
  "calmar",
  "cvar5",
  "winRate",
]) {
  assert(Object.hasOwn(oneMonth.factors[payload.selectedFactor], key), `missing Python period metric: ${key}`);
}

const adapted = api.adaptSchemaV4Payload(payload);
assert.equal(adapted.schema_version, 1);
assert.equal(adapted.runs.length, 1);
const run = adapted.runs[0];
assert.equal(Object.keys(api.validateFactorPortfolios(payload)).length, 64);
for (const mutate of [
  (copy) => { delete copy.factorPortfolios.mom_12m; },
  (copy) => { copy.factorPortfolios.mom_12m.weightingPolicyId = "equal_weight"; },
  (copy) => { copy.factorPortfolios.mom_12m.weights[0].weight += 0.01; },
]) {
  const copy = JSON.parse(JSON.stringify(payload));
  mutate(copy);
  assert.throws(
    () => api.validateFactorPortfolios(copy),
    /factorPortfolios|비중\/현금|canonical/,
    "the browser boundary must fail closed on a mutated factor portfolio",
  );
}
const noncanonicalPortfolioFactor = Object.keys(payload.factorPortfolios).find((factor) => (
  factor !== payload.selectedFactor
  && payload.factorPortfolios[factor]?.status === "available"
  && payload.factorPortfolios[factor]?.weights?.length > 0
));
assert(noncanonicalPortfolioFactor, "fixture must expose an available noncanonical factor portfolio");
const mutatedNoncanonicalConcentration = clonePayload(payload);
mutatedNoncanonicalConcentration.factorPortfolios[
  noncanonicalPortfolioFactor
].concentration.effectiveNames += 1;
assert.throws(
  () => api.validateFactorPortfolios(mutatedNoncanonicalConcentration),
  /factorPortfolios|concentration|집중도/,
  "every factorPortfolio concentration must be recomputed, not trusted only for the canonical target",
);

assert.equal(
  api.validateFactorDiagnostics(payload),
  payload.factorDiagnostics,
  "the complete untampered factorDiagnostics contract must pass the browser boundary",
);
const firstAvailableRankIc = payload.factorDiagnostics.rankIc.rows.find((row) => row.available === true);
const firstAvailableRedundancy = payload.factorDiagnostics.redundancy.rows.find(
  (row) => row.available === true,
);
const diagnosticAlias = payload.factorDiagnostics.scope.aliases[0]?.factor;
assert(firstAvailableRankIc && firstAvailableRedundancy && diagnosticAlias);

const diagnosticMutations = [
  {
    label: "Rank-IC mean outside [-1, 1]",
    mutate(copy) {
      copy.factorDiagnostics.rankIc.rows.find((row) => row.available === true).mean = 1.01;
    },
  },
  {
    label: "compatibility alias injected into the independent Rank-IC ranking",
    mutate(copy) {
      copy.factorDiagnostics.rankIc.rows[0].factor = diagnosticAlias;
    },
  },
  {
    label: "redundancy absolute correlation inconsistent with signed correlation",
    mutate(copy) {
      const row = copy.factorDiagnostics.redundancy.rows.find((item) => item.available === true);
      row.absCorr = Math.min(1, Math.abs(row.signedCorr) + 0.05);
      if (Math.abs(row.absCorr - Math.abs(row.signedCorr)) < 1e-12) row.absCorr -= 0.1;
    },
  },
  {
    label: "category aggregate no longer equals its factor rows",
    mutate(copy) {
      const row = copy.factorDiagnostics.categorySummary.find((item) => (
        Number.isFinite(Number(item.averageMeanRankIc))
      ));
      assert(row, "fixture must expose a finite category Rank-IC aggregate");
      row.averageMeanRankIc += 0.01;
    },
  },
  {
    label: "top redundancy pair ordering changed while ranks were relabeled",
    mutate(copy) {
      const pairs = copy.factorDiagnostics.redundancy.topPairs;
      assert(pairs.length >= 2, "fixture must expose at least two top redundancy pairs");
      [pairs[0], pairs[1]] = [pairs[1], pairs[0]];
      pairs[0].rank = 1;
      pairs[1].rank = 2;
    },
  },
];
for (const { label, mutate } of diagnosticMutations) {
  const copy = clonePayload(payload);
  mutate(copy);
  assert.throws(
    () => api.validateFactorDiagnostics(copy),
    /factorDiagnostics|Rank-IC|redundancy|category|pair/i,
    `browser factorDiagnostics validation must reject: ${label}`,
  );
}
const factorNames = run.factor_options.map((row) => row.factor);
const latestOneYear = run.factor_period_matrix.find(
  (row) => row.date === payload.data.asOf && row.window === "1Y",
);
assert.equal(
  api.defaultFactorForRun(run, factorNames, "", latestOneYear?.factors?.[0]),
  payload.selectedFactor,
  "the page must open on the canonical Python-selected factor, not an ex-post period leader",
);
const manualFactor = factorNames.find((factor) => factor !== payload.selectedFactor);
assert.equal(
  api.defaultFactorForRun(run, factorNames, manualFactor, latestOneYear?.factors?.[0]),
  manualFactor,
  "date/window changes must preserve an explicit user factor selection",
);
assert.equal(run.summary.data_as_of, payload.data.asOf);
assert.equal(run.summary.candidate_universe_size, payload.data.requestedCandidateCount);
assert.equal(run.summary.eligible_price_universe_size, payload.data.analyzedSecurityCount);
const candidateQualityRows = payload.quality.filter((row) => row.role === "candidate");
const freshCandidateRows = candidateQualityRows.filter((row) => row.last_date === payload.data.asOf);
assert.equal(run.data_quality_summary.price_quality_rows, candidateQualityRows.length);
assert.equal(run.data_quality_summary.fresh_price_rows, freshCandidateRows.length);
assert(
  Math.abs(
    run.data_quality_summary.fresh_price_ratio
    - (freshCandidateRows.length / candidateQualityRows.length)
  ) < 1e-12,
  "fresh-price ratio must be computed from candidate quality.last_date, never hard-coded",
);
assert.equal(run.data_quality_summary.capacity_status_counts, null);
assert.match(
  run.data_quality_summary.capacity_status_note,
  /미평가.*체결 용량 모델/,
  "capacity must remain N/A until an actual order-size/impact model exists",
);
assert.equal(
  JSON.stringify(run.data_quality_summary.latest_eligibility_exclusion_counts),
  JSON.stringify(payload.data.latestEligibilityExclusionCounts),
);
const requestedThroughText = api.canonicalRequestedThroughText(payload);
assert.match(requestedThroughText, /requestedThrough/);
assert.match(requestedThroughText, /asOf/);
assert(requestedThroughText.includes(payload.data.requestedThrough));
assert(requestedThroughText.includes(payload.data.asOf));
assert(requestedThroughText.includes(payload.data.sourceLabel));
assert.match(
  api.canonicalRequestedThroughText({
    data: {
      sourceLabel: "fixture",
      requestedThrough: "2026-07-12",
      asOf: "2026-07-10",
    },
  }),
  /주말.*직전 미국 거래일 종가/,
);
assert.match(
  api.canonicalRequestedThroughText({
    data: {
      sourceLabel: "fixture",
      requestedThrough: "2026-07-13",
      asOf: "2026-07-10",
    },
  }),
  /휴장일이거나 아직 완료되지 않은 거래일/,
);
const countDefinitions = api.canonicalCountDefinitions(payload);
for (const [value, definition] of [
  [payload.data.requestedCandidateCount, /요청\(requested\).*현재 유니버스 후보/],
  [payload.data.analyzedSecurityCount, /분석\(analyzed\).*가격 분석 가능/],
  [payload.data.latestEligibleSecurityCount, /최신 적격\(latest eligible\).*현재 편입 필터 모두 통과/],
]) {
  assert(countDefinitions.includes(Number(value).toLocaleString("ko-KR")));
  assert.match(countDefinitions, definition);
}
const universeScope = api.canonicalUniverseScopeEvidence(payload);
const universeSource = payload.sourceHealth.find(
  (row) => typeof row.point_in_time_universe === "boolean",
);
assert(universeSource, "actual provenance must declare point_in_time_universe");
assert.equal(universeScope.currentListed, true);
assert.equal(universeScope.pointInTime, false);
assert.match(universeScope.scope, /현재 상장 종목 중심/);
assert.match(universeScope.scope, /Point-in-time 유니버스 아님/);
assert.match(universeScope.evidence, /역사적 구성종목/);
assert.match(universeScope.evidence, /상장폐지/);
assert.match(universeScope.evidence, /ticker reuse/i);
for (const field of ["source", "status", "universe_provenance", "universe_source_mode", "universe_profile"]) {
  assert(
    universeScope.evidence.includes(String(universeSource[field])),
    `rendered universe evidence must consume sourceHealth.${field}`,
  );
}
assert(universeScope.evidence.includes(Number(universeSource.records).toLocaleString("ko-KR")));
const unknownUniverseScope = api.canonicalUniverseScopeEvidence({ sourceHealth: [], researchScope: {} });
assert.equal(unknownUniverseScope.currentListed, false);
assert.equal(unknownUniverseScope.pointInTime, null);
assert.match(unknownUniverseScope.scope, /시점성 미확인/);
assert.doesNotMatch(unknownUniverseScope.scope, /현재 상장/);
assert.equal(
  run.data_quality_summary.exclusion_counts_may_overlap,
  payload.data.funnel.exclusionCountsMayOverlap === true,
);
assert.equal(run.factor_backtest_series.length, Object.keys(payload.performance.factorCurves).length);
assert.deepEqual(
  Array.from(run.comparison_benchmark_series, (series) => series.symbol),
  ["SPY", "^IXIC", "QQQ"],
);
const fullPeriod = payload.performance.periods.find((period) => period.key === "FULL");
const commonPeriod = api.v4CommonEvaluationPeriod(payload);
assert(fullPeriod && commonPeriod, "the actual payload must expose an exact FULL common-evaluation window");
assert.equal(commonPeriod.startDate, fullPeriod.startDate);
assert.equal(commonPeriod.endDate, fullPeriod.endDate);
assert.equal(commonPeriod.startIndex, payload.performance.dates.indexOf(fullPeriod.startDate));
assert.equal(commonPeriod.endIndex, payload.performance.dates.lastIndexOf(fullPeriod.endDate));
assert.equal(commonPeriod.endIndex - commonPeriod.startIndex, fullPeriod.returnObservationCount);
assert.deepEqual(run.common_evaluation_period, commonPeriod);
for (const symbol of ["SPY", "^IXIC", "QQQ"]) {
  const series = run.comparison_benchmark_series.find((item) => item.symbol === symbol);
  const points = api.commonEvaluationSeriesPoints(series, commonPeriod);
  assert.equal(
    points.length,
    fullPeriod.returnObservationCount + 1,
    `${symbol} must preserve every common-evaluation point`,
  );
  assert.equal(points[0].date, fullPeriod.startDate, `${symbol} must start at the FULL boundary`);
  assert.equal(points.at(-1).date, fullPeriod.endDate, `${symbol} must end at the FULL boundary`);
  assert.equal(points[0].normalized, 1, `${symbol} must use the common FULL base`);
  const chartReturn = points.at(-1).normalized - 1;
  const tableReturn = fullPeriod.benchmarks[symbol].cumulativeReturn;
  assert(
    Math.abs(chartReturn - tableReturn) < 1e-12,
    `${symbol} chart endpoint ${chartReturn} must equal the FULL table ${tableReturn}`,
  );
}
assert(
  fullPeriod.benchmarks.QQQ.cumulativeReturn > 1,
  "the actual-payload regression must retain QQQ's greater-than-100% FULL return",
);
const shiftedCommonPeriod = {
  startDate: "2026-01-05",
  endDate: "2026-01-07",
  returnObservationCount: 2,
};
const shiftedPoints = api.commonEvaluationSeriesPoints({
  dates: ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"],
  equity: [2, 3, 4, 6],
}, shiftedCommonPeriod);
assert.deepEqual(
  Array.from(shiftedPoints, (point) => point.normalized),
  [1, 4 / 3, 2],
  "common evaluation normalization must use the exact period start index, not curve index zero",
);
const segmentedGap = api.commonEvaluationSeriesSegments({
  dates: ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"],
  equity: [3, 4, null, 5, 6],
}, {
  startDate: "2026-01-05",
  endDate: "2026-01-09",
  returnObservationCount: 4,
});
assert.equal(segmentedGap.available, true);
assert.equal(segmentedGap.missingCount, 1);
assert.deepEqual(Array.from(segmentedGap.missingDates), ["2026-01-07"]);
assert.equal(segmentedGap.segments.length, 2, "an internal gap must split, never connect, the line");
assert.deepEqual(
  Array.from(segmentedGap.segments, (segment) => Array.from(segment, (point) => point.date)),
  [["2026-01-05", "2026-01-06"], ["2026-01-08", "2026-01-09"]],
);
assert.equal(segmentedGap.points.at(-1).normalized, 2, "segmented endpoints must retain the exact FULL return");
for (const [label, invalidNav] of [
  ["null", null],
  ["undefined", undefined],
  ["zero", 0],
  ["negative", -0.01],
  ["numeric string", "4"],
]) {
  assert.deepEqual(
    Array.from(api.commonEvaluationSeriesPoints({
      dates: ["2026-01-05", "2026-01-06", "2026-01-07"],
      equity: [3, invalidNav, 6],
    }, shiftedCommonPeriod)),
    [],
    `FULL common evaluation must fail closed on a raw ${label} NAV`,
  );
  assert.deepEqual(
    Array.from(api.seriesPointsThroughDate({
      dates: ["2026-01-05", "2026-01-06", "2026-01-07"],
      equity: [3, invalidNav, 6],
      drawdown: [0, null, 0],
    }, "2026-01-07", 3)),
    [],
    `generic chart extraction must fail closed on a raw ${label} NAV`,
  );
}
const terminallyUnavailableFactor = Object.entries(payload.performance.factorCurves)
  .find(([, curve]) => curve.at(-1) === null);
assert(terminallyUnavailableFactor, "actual payload fixture must retain a terminally unavailable diagnostic factor");
const unavailableFactorSeries = run.factor_backtest_series.find(
  (series) => series.factor === terminallyUnavailableFactor[0],
);
assert.deepEqual(
  Array.from(api.commonEvaluationSeriesPoints(unavailableFactorSeries, commonPeriod)),
  [],
  "a diagnostic factor with terminally unavailable NAV must not render as a false -100% loss",
);
assert(run.factor_period_matrix.length >= 300, "restored date/window exploration matrix must be populated");
assert(run.factor_leaders.length >= 300, "restored 30-session leader views must be populated");
assert(run.factor_weight_snapshots.length > 0, "restored factor weight and ensemble views need Python snapshots");
for (const snapshot of run.factor_score_snapshots) {
  const portfolio = payload.factorPortfolios[snapshot.factor];
  assert(portfolio, `missing source factorPortfolio for ${snapshot.factor}`);
  assert.equal(snapshot.score_scope, "schema_v4_current_python_portfolio_top_constituents");
  assert.equal(snapshot.snapshot_complete, false);
  assert.equal(snapshot.rows.length, portfolio.weights.length);
  assert.equal(snapshot.raw_available_count, snapshot.rows.length);
  assert.equal(snapshot.stored_row_count, snapshot.rows.length);
  assert.equal(snapshot.upstream_final_eligible_count, portfolio.eligibleSecurityCount);
  assert(
    snapshot.raw_available_count <= snapshot.upstream_final_eligible_count,
    "stored current constituents must not masquerade as the full eligible score universe",
  );
}
assert.equal(
  api.storedScenarioRowLimit(run, payload.selectedFactor),
  payload.factorPortfolios[payload.selectedFactor].weights.length,
  "top-N controls must stop at the number of actually stored rows",
);

const sourceHealthText = api.formatSourceHealth(run.data_quality_summary.source_health, {
  requestedCandidateCount: payload.data.requestedCandidateCount,
  providerReturnedCandidateCount: payload.data.providerReturnedCandidateCount,
  latestEligibleSecurityCount: payload.data.latestEligibleSecurityCount,
});
assert.match(sourceHealthText, /전체 결과: 공급자 사용 가능/);
assert.match(sourceHealthText, /Yahoo chart 보강/);
assert.match(sourceHealthText, /Nasdaq 최신일 보강/);
assert.match(sourceHealthText, /실패/);
assert.match(sourceHealthText, /최종 사용 가능 여부는 앞의 전체 결과/);

const selectedPolicyRows = payload.factorPolicyRanking.filter(
  (row) => (row.policy_id || row.weightingPolicyId) === payload.selectedWeightingPolicy,
);
const eligibleFactors = new Set(
  selectedPolicyRows.filter((row) => row.selection_eligible === true).map((row) => row.factor),
);
assert(eligibleFactors.size > 0, "selected policy must expose eligible exploration candidates");
for (const matrix of run.factor_period_matrix) {
  assert(
    matrix.factors.every((factor) => eligibleFactors.has(factor)),
    "period-best exploration must exclude guardrail-ineligible factors",
  );
}
const gapRow = selectedPolicyRows.find((row) => row.factor === "gap_resistant");
if (gapRow) {
  assert.equal(gapRow.selection_eligible, false, "the extreme-event factor fixture must be excluded");
  assert(
    run.factor_backtest_series.some((series) => series.factor === "gap_resistant"),
    "excluded factors must remain available as diagnostic curves",
  );
  assert(
    run.factor_options.some((option) => option.factor === "gap_resistant" && option.selection_eligible === false),
    "the selector must label excluded diagnostic factors",
  );
  assert(
    run.factor_leaders.every((leader) => leader.best_factor !== "gap_resistant"),
    "gap_resistant must not become a default period-best candidate",
  );
}

assert.equal(run.current_research_target.factor, payload.selectedFactor);
assert.equal(run.current_research_target.weights.length, payload.currentResearchTarget.weights.length);
assert.equal(Object.keys(run.factor_current_research_targets).length, 64);
for (const [factor, portfolio] of Object.entries(payload.factorPortfolios)) {
  const adaptedTarget = run.factor_current_research_targets[factor];
  assert(adaptedTarget, `missing adapted current target for ${factor}`);
  assert.equal(adaptedTarget.factor, factor);
  assert.equal(adaptedTarget.weightingPolicyId, payload.selectedWeightingPolicy);
  assert.equal(adaptedTarget.signalDate, payload.data.asOf);
  assert.equal(adaptedTarget.weights.length, portfolio.weights.length);
  assert.equal(adaptedTarget.cashWeight, portfolio.cashWeight);
}
assert(run.holdings.every((row) => row.factor === payload.selectedFactor));
assert(
  run.holdings.every((row) => row.history_source !== undefined),
  "run.holdings must contain only actual history/fallback rows, never current target clones",
);
if (payload.selectedBacktestHoldingHistory) {
  assert.equal(run.backtest_holding_sessions.length, 21);
  assert.equal(run.backtest_holding_history.sourceKind, "selected_backtest_holding_history");
} else {
  assert.equal(run.backtest_holding_sessions.length, 1);
  assert.equal(run.backtest_holding_history.sourceKind, "legacy_backtest_held_fallback");
}

const historyFixture = JSON.parse(JSON.stringify(payload));
const fixtureDates = payload.performance.dates.slice(-21);
const symbolNames = new Map();
historyFixture.selectedBacktestHoldingHistory.sessions.forEach((session) => {
  session.weights.forEach((row) => symbolNames.set(row.symbol, row.name));
});
const sidecarSymbols = [...symbolNames.entries()].sort(([left], [right]) => left.localeCompare(right));
const sidecarSymbolIndexes = new Map(sidecarSymbols.map(([symbol], index) => [symbol, index]));
const compactSessions = historyFixture.selectedBacktestHoldingHistory.sessions.map((session) => ({
  valuationAvailable: session.valuationAvailable,
  cashWeight: session.cashWeight,
  executionStatus: session.executionStatus,
  lastSignalDate: session.lastSignalDate,
  lastExecutionDate: session.lastExecutionDate,
  weights: session.weights.map((row) => [sidecarSymbolIndexes.get(row.symbol), row.weight]),
}));
const diagnosticFactor = "gap_resistant";
const factorIds = payload.factorDefinitions.map((row) => row.factor).sort();
const independentFactorCount = payload.factorDefinitions.filter((row) => (
  row.selection_eligible === true && row.compatibility_alias_of === null
)).length;
const sidecarData = {
  contract: "momentum-factor-holding-history-sidecar",
  contractVersion: 1,
  resultKey: payload.resultKey,
  selectedWeightingPolicy: payload.selectedWeightingPolicy,
  weightTiming: "last_complete_close_after_execution_processing",
  startDate: fixtureDates[0],
  endDate: fixtureDates.at(-1),
  sessionCount: fixtureDates.length,
  dates: fixtureDates,
  factorCount: factorIds.length,
  independentFactorCount,
  diagnosticFactorCount: factorIds.length - independentFactorCount,
  factorDefinitionSha256: payload.meta.factorDefinitionSha256,
  policyDefinitionSha256: payload.meta.policyDefinitionSha256,
  symbols: sidecarSymbols,
  factors: Object.fromEntries(factorIds.map((factor) => [
    factor,
    {
      factor,
      weightingPolicyId: payload.selectedWeightingPolicy,
      resultKey: payload.resultKey,
      sessions: compactSessions,
    },
  ])),
};
const sidecarBytes = new TextEncoder().encode(api.canonicalString(sidecarData));
const sidecarDigest = createHash("sha256").update(sidecarBytes).digest("hex");
historyFixture.factorHoldingHistorySidecar = {
  contract: sidecarData.contract,
  contractVersion: 1,
  storage: "embedded",
  path: `data/factor-holding-history/${payload.resultKey}.json`,
  bytes: sidecarBytes.byteLength,
  sha256: sidecarDigest,
  resultKey: payload.resultKey,
  selectedWeightingPolicy: payload.selectedWeightingPolicy,
  weightTiming: sidecarData.weightTiming,
  startDate: sidecarData.startDate,
  endDate: sidecarData.endDate,
  sessionCount: sidecarData.sessionCount,
  factorCount: sidecarData.factorCount,
  independentFactorCount: sidecarData.independentFactorCount,
  diagnosticFactorCount: sidecarData.diagnosticFactorCount,
  data: sidecarData,
};
historyFixture.__factorHoldingHistorySidecarData = await api.loadV4FactorHoldingHistorySidecar(
  historyFixture,
);
assert.deepEqual(
  Object.keys(historyFixture.selectedBacktestHoldingHistory).sort(),
  [
    "contractVersion",
    "factor",
    "weightingPolicyId",
    "weightTiming",
    "startDate",
    "endDate",
    "sessionCount",
    "sessions",
  ].sort(),
  "synthetic history top-level fields must match the exact backend contract",
);
for (const session of historyFixture.selectedBacktestHoldingHistory.sessions) {
  assert.deepEqual(
    Object.keys(session).sort(),
    [
      "date",
      "valuationAvailable",
      "cashWeight",
      "executionStatus",
      "lastSignalDate",
      "lastExecutionDate",
      "weights",
    ].sort(),
    "synthetic history session fields must match the exact backend contract",
  );
  assert(["none", "executed", "executed_partial_unpriceable_targets", "blocked_missing_held_quote", "blocked_all_targets_unpriceable"].includes(session.executionStatus));
  for (const weight of session.weights) {
    assert.deepEqual(
      Object.keys(weight).sort(),
      ["rank", "symbol", "name", "weight"].sort(),
      "synthetic history weight fields must match the exact backend contract",
    );
  }
}
const historyRun = api.adaptSchemaV4Payload(historyFixture).runs[0];
assert.equal(historyRun.backtest_holding_sessions.length, 21);
assert.equal(historyRun.backtest_holding_history.contractVersion, 1);
assert.equal(historyRun.backtest_holding_history.sessionCount, 21);
assert.equal(historyRun.backtest_holding_history.weightTiming, "last_complete_close_after_execution_processing");
assert(historyRun.backtest_holding_sessions.every((session) => session.valuationAvailable === true));
assert(historyRun.backtest_holding_sessions.every((session) => (
  [
    "none",
    "executed",
    "executed_partial_unpriceable_targets",
    "blocked_missing_held_quote",
    "blocked_all_targets_unpriceable",
  ].includes(session.executionStatus)
)));
assert(historyRun.backtest_holding_sessions.some((session) => session.executionStatus === "executed"));
assert.equal(new Set(historyRun.holdings.map((row) => row.date)).size, 21);
const selectedHistory = api.selectedDailyWeightRows(
  historyRun,
  payload.data.asOf,
  "1Y",
  payload.selectedFactor,
);
assert.equal(selectedHistory.dateCount, 21);
assert.equal(selectedHistory.targetRows.length, payload.currentResearchTarget.weights.length);
const otherFactorHistory = api.selectedDailyWeightRows(
  historyRun,
  payload.data.asOf,
  "1Y",
  "gap_resistant",
);
assert.equal(otherFactorHistory.sourceKind, "factor_backtest_holding_history_sidecar");
assert.equal(otherFactorHistory.dateCount, 21);
assert(otherFactorHistory.rows.length > 0);
assert.equal(otherFactorHistory.targetRows.length, payload.factorPortfolios.gap_resistant.weights.length);
assert.equal(otherFactorHistory.target.status, "available");
assert.equal(otherFactorHistory.target.cashWeight, payload.factorPortfolios.gap_resistant.cashWeight);
assert.equal(otherFactorHistory.target.factor, "gap_resistant");
assert.notDeepEqual(
  Array.from(otherFactorHistory.targetRows, (row) => [row.symbol, row.targetWeight]),
  Array.from(selectedHistory.targetRows, (row) => [row.symbol, row.targetWeight]),
  "a noncanonical factor must use its exact factorPortfolio, not a canonical target clone",
);
const noSidecarPayload = JSON.parse(JSON.stringify(payload));
delete noSidecarPayload.factorHoldingHistorySidecar;
delete noSidecarPayload.__factorHoldingHistorySidecarData;
const noSidecarRun = api.adaptSchemaV4Payload(noSidecarPayload).runs[0];
const noSidecarDiagnostic = api.selectedDailyWeightRows(
  noSidecarRun,
  payload.data.asOf,
  "1Y",
  diagnosticFactor,
);
assert.equal(noSidecarDiagnostic.sourceKind, "factor_history_unavailable");
assert.equal(noSidecarDiagnostic.rows.length, 0, "a new payload must not reuse stale sidecar state");
assert.equal(noSidecarDiagnostic.target.factor, diagnosticFactor);
assert.equal(
  noSidecarDiagnostic.target.cashWeight,
  payload.factorPortfolios[diagnosticFactor].cashWeight,
  "current factor target must remain independently available when history is absent",
);

const externalPayload = JSON.parse(JSON.stringify(historyFixture));
externalPayload.factorHoldingHistorySidecar.storage = "external";
delete externalPayload.factorHoldingHistorySidecar.data;
delete externalPayload.__factorHoldingHistorySidecarData;
const loadedSidecar = await api.loadV4FactorHoldingHistorySidecar(externalPayload, async (path) => ({
  ok: path === externalPayload.factorHoldingHistorySidecar.path,
  arrayBuffer: async () => sidecarBytes.buffer,
}));
assert.equal(loadedSidecar.resultKey, payload.resultKey);
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    { ...externalPayload, factorHoldingHistorySidecar: { ...externalPayload.factorHoldingHistorySidecar, bytes: sidecarBytes.byteLength + 1 } },
    async () => ({ ok: true, arrayBuffer: async () => sidecarBytes.buffer }),
  ),
  /크기/,
);
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    { ...externalPayload, factorHoldingHistorySidecar: { ...externalPayload.factorHoldingHistorySidecar, sha256: "0".repeat(64) } },
    async () => ({ ok: true, arrayBuffer: async () => sidecarBytes.buffer }),
  ),
  /SHA-256/,
);
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(externalPayload, async () => ({ ok: false })),
  /불러오지 못했습니다/,
);

function mutatedExternalSidecar(mutate) {
  const data = JSON.parse(JSON.stringify(sidecarData));
  mutate(data);
  const bytes = new TextEncoder().encode(api.canonicalString(data));
  const copy = JSON.parse(JSON.stringify(externalPayload));
  copy.factorHoldingHistorySidecar.bytes = bytes.byteLength;
  copy.factorHoldingHistorySidecar.sha256 = createHash("sha256").update(bytes).digest("hex");
  return { payload: copy, bytes };
}

const missingFactor = mutatedExternalSidecar((data) => {
  delete data.factors[Object.keys(data.factors)[0]];
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    missingFactor.payload,
    async () => ({ ok: true, arrayBuffer: async () => missingFactor.bytes.buffer }),
  ),
  /64개 팩터/,
);

const invalidAllocation = mutatedExternalSidecar((data) => {
  const factor = Object.keys(data.factors)[0];
  data.factors[factor].sessions[0].cashWeight = 0.99;
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    invalidAllocation.payload,
    async () => ({ ok: true, arrayBuffer: async () => invalidAllocation.bytes.buffer }),
  ),
  /배분\/정렬/,
);

const noncanonicalSession = mutatedExternalSidecar((data) => {
  const factor = Object.keys(data.factors)[0];
  data.factors[factor].sessions[0].unexpected = true;
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    noncanonicalSession.payload,
    async () => ({ ok: true, arrayBuffer: async () => noncanonicalSession.bytes.buffer }),
  ),
  /metadata/,
);

const tickMarks = api.dateTickMarks(payload.performance.dates);
assert(tickMarks.length >= 6 && tickMarks.length <= 12, "the x-axis must expose 6-12 clean date categories");
assert.equal(new Set(tickMarks.map((tick) => tick.label)).size, tickMarks.length, "x-axis labels must not duplicate at the final date");
const yTicks = api.niceReturnTicks(-0.18, 1.63);
assert(yTicks.length >= 4 && yTicks.length <= 7, "the y-axis must use 4-7 clean percentage ticks");
assert(yTicks.includes(0), "the cumulative-return axis must include zero");
assert(Math.abs(api.v4CurveReturn([1, 1.05, 1.1], 2, 2) - 0.1) < 1e-12);

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
assert.equal(new Set(ids).size, ids.length, "HTML ids must remain unique");
for (const id of [
  "performance-metrics-table",
  "backtest-chart",
  "factor-return-chart",
  "window-comparison-chart",
  "leader-trend-chart",
  "weight-chart",
  "ensemble-weight-chart",
  "joint-ranking-chart",
  "canonical-component-chart",
]) {
  assert(ids.includes(id), `missing chart/table host: ${id}`);
}

console.log("PASS schema-v4 diagnostics/portfolio/performance/holding tamper checks, benchmark parity, axes, and restored UI contracts");
