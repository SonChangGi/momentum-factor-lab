import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const publishedManifest = JSON.parse(readFileSync("docs/data/grid/v1/manifest.json", "utf8"));
const publishedDetail = JSON.parse(readFileSync("docs/data/dashboard.json", "utf8"));
let mockResponse;
let lastFetch;
const context = vm.createContext({
  console,
  crypto: webcrypto,
  fetch: async (url, options) => {
    lastFetch = { url, options };
    return mockResponse;
  },
  setTimeout,
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
});
vm.runInContext(source, context, { filename: "momentum_factor_lab/web/dashboard.js" });
const api = context.__MFL_WEB_TESTS__;
assert(api, "web contract test API must be exposed without a DOM");

for (const entry of publishedManifest.entries) {
  const detail = JSON.parse(readFileSync(`docs/data/grid/v1/${entry.detail.path}`, "utf8"));
  const summary = JSON.parse(readFileSync(`docs/data/grid/v1/${entry.summary.path}`, "utf8"));
  assert.equal(
    await api.validateResult(entry, detail, summary),
    detail.factorPolicyRanking.find((row) => row.selected),
    `published preset ${entry.presetId} must pass the complete browser boundary`,
  );
}

const htmlIds = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
assert.equal(
  new Set(htmlIds).size,
  htmlIds.length,
  "the dashboard HTML must not contain duplicate element ids",
);
const staticSelectorIds = [...source.matchAll(/\$\("#([^"]+)"\)/g)]
  .map((match) => match[1].split(/[ .:[>+~]/, 1)[0]);
assert.deepEqual(
  [...new Set(staticSelectorIds)].filter((id) => !htmlIds.includes(id)),
  [],
  "every static dashboard.js id selector must resolve in the source HTML",
);
assert.deepEqual(
  Array.from(api.INPUT_FIELDS, (field) => field.id).filter((id) => !htmlIds.includes(id)),
  [],
  "every canonical public research input must have a web control",
);
assert.equal(
  api.canonicalString({
    zero: 0.0,
    negativeZero: -0.0,
    one: 1.0,
    tiny: 1e-7,
    fixed: 1e-6,
    large: 1e30,
    unicode: "한글",
  }),
  '{"fixed":0.000001,"large":1e+30,"negativeZero":0,"one":1,"tiny":1e-7,"unicode":"한글","zero":0}',
  "the browser canonical encoder must match the Python RFC 8785 edge-number fixture",
);
assert.deepEqual(
  JSON.parse(JSON.stringify(api.researchInputsFromNormalizedInputs(
    publishedDetail.resultIdentity.keyParts.normalizedInputs,
  ))),
  publishedDetail.researchInputs,
  "the browser public-input mapping must exactly match the canonical Python artifact",
);

const normalizedInputs = (topN) => ({
  absolute_guardrail_version: "absolute-factor-policy-v1",
  end_date: "2024-05-31",
  evaluation_window_days: 756,
  joint_selection_version: "joint-factor-policy-v1",
  liquidity_lookback_days: 63,
  live: true,
  max_extreme_daily_return: 0.8,
  max_price_missing_ratio: 0.05,
  max_volume_missing_ratio: 0.1,
  max_weight: 0.1,
  min_avg_dollar_volume: 5_000_000,
  min_avg_volume: 100_000,
  min_daily_risk_observations: 504,
  min_evaluation_observations: 504,
  min_history_days: 252,
  min_liquidity_observations: 42,
  min_price: 5,
  rebalance_frequency: "ME",
  slippage_bps: 5,
  top_n: topN,
  transaction_cost_bps: 5,
  selection_min_sharpe: 0,
  selection_max_drawdown: 0.6,
  selection_max_annualized_cost_drag: 0.02,
  selection_min_effective_names: 10,
  selection_max_target_hhi: 0.15,
  selection_max_target_weight: 0.15,
  selection_max_abs_security_day_contribution: 0.25,
  selection_max_security_absolute_contribution_share: 0.35,
  selection_max_leave_one_security_cagr_delta: 0.25,
  selection_extreme_event_action: "exclude",
  selection_extreme_event_penalty_points: 20,
});
const fixtureAnalyzedSymbols = Array.from(
  { length: 2_861 },
  (_value, index) => `SYM${String(index + 1).padStart(4, "0")}`,
);
const priceSources = fixtureAnalyzedSymbols.map((symbol) => ({
  symbol,
  price_source: "actual-provider-fixture",
}));
const sourceHealth = [{ source: "actual-provider-fixture", status: "ok" }];
const fixtureInputSha256 = {
  prices: "6".repeat(64),
  volumes: "7".repeat(64),
  dollarVolumes: "8".repeat(64),
  rawCloses: "9".repeat(64),
  requestedSymbols: "a".repeat(64),
  returnedSymbols: "b".repeat(64),
  universeRecords: "e".repeat(64),
  priceSources: createHash("sha256").update(api.canonicalString(priceSources)).digest("hex"),
  dataSources: createHash("sha256").update(api.canonicalString(sourceHealth)).digest("hex"),
};
const fixtureCandidateSymbolsSha256 = createHash("sha256")
  .update(api.canonicalString(fixtureAnalyzedSymbols))
  .digest("hex");

const makeEntry = (digit, topN) => {
  const inputs = normalizedInputs(topN);
  const keyParts = {
    identityVersion: "momentum-result-identity-v1",
    canonicalJsonVersion: "rfc8785-jcs-v1",
    normalizedInputs: inputs,
    marketSnapshot: {
      sourceMode: "live_market",
      sourceLabel: "actual-provider-fixture",
      provider: "actual-provider-fixture",
      priceBasis: "provider_adjusted_close",
      volumeBasis: "raw_close_x_raw_volume",
      rawCloseProxySymbolCount: 0,
      requestedThrough: "2024-05-31",
      dataAsOf: "2024-05-31",
      inputSha256: fixtureInputSha256,
      requestedCandidateCount: 2_865,
      providerReturnedCandidateCount: 2_861,
      analyzedSecurityCount: 2_861,
      candidateSymbolsSha256: fixtureCandidateSymbolsSha256,
      snapshotTag: digit,
    },
  };
  const canonicalKeyPartsJson = api.canonicalString(keyParts);
  const resultKey = createHash("sha256").update(canonicalKeyPartsJson).digest("hex");
  const identity = {
    identityVersion: "momentum-result-identity-v1",
    resultKey,
    keyParts,
    canonicalKeyPartsJson,
  };
  return {
    normalizedInputs: inputs,
    resultKey,
    identity,
    detail: { path: `results/${resultKey}.json`, sha256: "a".repeat(64), bytes: 100 },
    summary: { path: `summaries/${resultKey}.json`, sha256: "b".repeat(64), bytes: 50 },
  };
};

const first = makeEntry("1", 20);
const second = makeEntry("2", 30);
first.presetId = "latest-top20";
second.presetId = "latest-top30";
const manifest = {
  schemaVersion: 1,
  contract: "momentum-static-result-grid",
  gridVersion: "v1",
  bounded: true,
  maxEntries: 64,
  entryCount: 2,
  defaultResultKey: first.resultKey,
  entries: [first, second],
};

assert.equal(api.validateManifest(manifest), manifest);
assert.equal(api.resolveExactEntry(manifest, normalizedInputs(20)).resultKey, first.resultKey);
assert.equal(api.resolveExactEntry(manifest, normalizedInputs(21)), null, "static resolver must not choose a nearest tuple");
assert.deepEqual(
  [...api.rowReasonCodes({
    guardrail_breaches: ["maximum_drawdown_magnitude"],
    exclusion_reasons: [{ code: "must_not_stringify_object" }],
    exclusion_reason_codes: ["duplicate_alias"],
  })],
  ["maximum_drawdown_magnitude", "duplicate_alias"],
  "structured exclusion reasons must render stable codes instead of [object Object]",
);

const manifestBytes = new TextEncoder().encode(JSON.stringify(manifest));
mockResponse = {
  ok: true,
  arrayBuffer: async () => manifestBytes.buffer,
};
assert.deepEqual(
  JSON.parse(JSON.stringify(await api.fetchJson("https://example.test/manifest.json", "manifest"))),
  manifest,
  "manifest bootstrap must parse without an artifact reference",
);
const verifiedBytes = new TextEncoder().encode('{"ok":true}');
mockResponse = {
  ok: true,
  arrayBuffer: async () => verifiedBytes.buffer,
};
assert.deepEqual(
  JSON.parse(JSON.stringify(await api.fetchJson("https://example.test/detail.json", "detail", {
    bytes: verifiedBytes.byteLength,
    sha256: createHash("sha256").update(verifiedBytes).digest("hex"),
  }))),
  { ok: true },
  "referenced artifacts must pass raw byte and SHA-256 verification before JSON parse",
);

const roundTripSearch = api.searchForRequest(
  second.resultKey,
  second.normalizedInputs,
  second.presetId,
);
const roundTrip = api.requestFromSearch(manifest, roundTripSearch);
assert.equal(roundTrip.error, null);
assert.equal(roundTrip.entry.resultKey, second.resultKey, "exact URL state must round-trip to the same static entry");
assert.equal(api.canonicalString(roundTrip.requestedInputs), api.canonicalString(second.normalizedInputs));

const rotatedFirst = makeEntry("3", 20);
const rotatedSecond = makeEntry("4", 30);
rotatedFirst.presetId = first.presetId;
rotatedSecond.presetId = second.presetId;
const rotatedManifest = {
  ...manifest,
  defaultResultKey: rotatedFirst.resultKey,
  entries: [rotatedFirst, rotatedSecond],
};
const rotatedStaticRequest = api.requestFromSearch(rotatedManifest, roundTripSearch);
assert.equal(rotatedStaticRequest.recoveredFromRotatedResult, true);
assert.equal(
  rotatedStaticRequest.baseEntry.resultKey,
  rotatedSecond.resultKey,
  "a shared static URL must recover through its stable preset after result-key rotation",
);
assert.equal(rotatedStaticRequest.entry.resultKey, rotatedSecond.resultKey);

const unsupportedBeforeRotation = new URLSearchParams(api.searchForRequest(
  first.resultKey,
  { ...first.normalizedInputs, top_n: 21 },
  first.presetId,
));
const rotatedApiRequest = api.requestFromSearch(
  rotatedManifest,
  `?${unsupportedBeforeRotation.toString()}`,
);
assert.equal(rotatedApiRequest.recoveredFromRotatedResult, true);
assert.equal(rotatedApiRequest.baseEntry.resultKey, rotatedFirst.resultKey);
assert.equal(rotatedApiRequest.requestedInputs.top_n, 21);
assert.equal(rotatedApiRequest.entry, null);
assert.match(rotatedApiRequest.error, /Python backend\/API/);

const legacyRotatedRequest = api.requestFromSearch(
  rotatedManifest,
  api.searchForRequest(first.resultKey, { ...first.normalizedInputs, top_n: 21 }),
);
assert.equal(legacyRotatedRequest.baseEntry.resultKey, rotatedFirst.resultKey);
assert.equal(legacyRotatedRequest.requestedInputs.top_n, 21);

const unsupportedParams = new URLSearchParams(api.searchForRequest(first.resultKey, first.normalizedInputs));
unsupportedParams.set("top_n", "21");
const unsupported = api.requestFromSearch(manifest, `?${unsupportedParams.toString()}`);
assert.equal(unsupported.entry, null);
assert.match(unsupported.error, /Python backend\/API/);
const historicalUnsupportedInputs = {
  ...first.normalizedInputs,
  end_date: "2024-04-30",
  top_n: 21,
};
const preparedLocalRequest = api.localApiRequestFromStaticState(manifest, historicalUnsupportedInputs);
assert.equal(preparedLocalRequest.baseEntry.resultKey, manifest.defaultResultKey);
assert.equal(preparedLocalRequest.requestedInputs.end_date, first.normalizedInputs.end_date);
assert.equal(preparedLocalRequest.requestedInputs.top_n, 21);
const apiReloadSearch = api.searchForRequest(
  preparedLocalRequest.baseEntry.resultKey,
  preparedLocalRequest.requestedInputs,
);
assert.equal(new URLSearchParams(apiReloadSearch).get("result"), manifest.defaultResultKey);

const localApiInputs = api.researchInputsFromNormalizedInputs(normalizedInputs(21));
assert.equal(localApiInputs.version, "research-inputs-v1");
assert.equal(localApiInputs.topN, 21);
assert.equal(localApiInputs.evaluationYears, 3);
assert.equal(localApiInputs.selectionMaxAbsSecurityDayContribution, 0.25);
assert.equal(localApiInputs.selectionExtremeEventAction, "exclude");
const localApiResponseBytes = new TextEncoder().encode('{"accepted":true}');
mockResponse = {
  ok: true,
  status: 202,
  arrayBuffer: async () => localApiResponseBytes.buffer,
};
assert.deepEqual(
  JSON.parse(JSON.stringify((await api.fetchLocalApiJson("/api/runs", {
    method: "POST",
    body: localApiInputs,
  })).body)),
  { accepted: true },
);
assert.equal(lastFetch.url, "http://127.0.0.1:8765/api/runs");
assert.equal(lastFetch.options.method, "POST");
assert.deepEqual(JSON.parse(lastFetch.options.body), JSON.parse(JSON.stringify(localApiInputs)));

const policies = [
  "equal_weight",
  "capped_linear_rank",
  "capped_vol_adjusted_rank",
  "score_liquidity_rank",
];
const fixtureResearchInputs = {
  version: "research-inputs-v1",
  rebalanceFrequency: "ME",
  evaluationYears: 3,
  evaluationWindowDays: 756,
  topN: 20,
  maxWeight: 0.1,
  transactionCostBps: 5,
  slippageBps: 5,
  minHistoryDays: 252,
  minPrice: 5,
  minAvgDollarVolume: 5_000_000,
  minAvgVolume: 100_000,
  liquidityLookbackDays: 63,
  minLiquidityObservations: 42,
  maxPriceMissingRatio: 0.05,
  maxVolumeMissingRatio: 0.1,
  maxExtremeDailyReturn: 0.8,
  selectionMinSharpe: 0,
  selectionMaxDrawdown: 0.6,
  selectionMaxAnnualizedCostDrag: 0.02,
  selectionMinEffectiveNames: 10,
  selectionMaxTargetHhi: 0.15,
  selectionMaxTargetWeight: 0.15,
  selectionMaxAbsSecurityDayContribution: 0.25,
  selectionMaxSecurityAbsoluteContributionShare: 0.35,
  selectionMaxLeaveOneSecurityCagrDelta: 0.25,
  selectionExtremeEventAction: "exclude",
  selectionExtremeEventPenaltyPoints: 20,
};
const fixtureGuardrailProfile = {
  id: "absolute-factor-policy-v1",
  version: 1,
  policyNeutral: true,
  rules: [
    {
      id: "minimum_sharpe",
      metric: "sharpe",
      operator: ">=",
      threshold: fixtureResearchInputs.selectionMinSharpe,
      unit: "ratio",
    },
    {
      id: "maximum_drawdown_magnitude",
      metric: "max_drawdown",
      operator: ">=",
      threshold: -fixtureResearchInputs.selectionMaxDrawdown,
      unit: "fraction",
    },
    {
      id: "maximum_annualized_cost_drag",
      metric: "annualized_cost_drag",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxAnnualizedCostDrag,
      unit: "fraction_per_year",
    },
    {
      id: "minimum_historical_target_effective_names",
      metric: "min_target_effective_names",
      operator: ">=",
      threshold: fixtureResearchInputs.selectionMinEffectiveNames,
      unit: "names",
    },
    {
      id: "minimum_current_target_effective_names",
      metric: "current_target_effective_names",
      operator: ">=",
      threshold: fixtureResearchInputs.selectionMinEffectiveNames,
      unit: "names",
    },
    {
      id: "maximum_historical_target_hhi",
      metric: "max_target_hhi",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxTargetHhi,
      unit: "fraction",
    },
    {
      id: "maximum_current_target_hhi",
      metric: "current_target_hhi",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxTargetHhi,
      unit: "fraction",
    },
    {
      id: "maximum_historical_target_weight",
      metric: "max_target_weight",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxTargetWeight,
      unit: "fraction",
    },
    {
      id: "maximum_current_target_weight",
      metric: "current_target_max_weight",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxTargetWeight,
      unit: "fraction",
    },
    {
      id: "maximum_security_day_contribution",
      metric: "max_abs_security_day_contribution",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxAbsSecurityDayContribution,
      unit: "portfolio_return_fraction",
    },
    {
      id: "maximum_security_absolute_contribution_share",
      metric: "max_security_absolute_contribution_share",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxSecurityAbsoluteContributionShare,
      unit: "fraction",
    },
    {
      id: "maximum_leave_one_security_cagr_delta",
      metric: "max_abs_leave_one_security_cagr_delta",
      operator: "<=",
      threshold: fixtureResearchInputs.selectionMaxLeaveOneSecurityCagrDelta,
      unit: "cagr_fraction",
    },
  ],
  requiredContracts: {
    completePolicyInputs: true,
    completeExecutionCoverage: true,
    currentTargetAvailable: true,
    contributionDiagnosticsComplete: true,
  },
  extremeEventAction: fixtureResearchInputs.selectionExtremeEventAction,
  extremeEventPenaltyPoints: fixtureResearchInputs.selectionExtremeEventPenaltyPoints,
};
const independentFactors = [
  "factor_alpha",
  ...Array.from({ length: 60 }, (_value, index) => `factor_${String(index + 1).padStart(2, "0")}`),
];
const aliasFactors = ["alias_one", "alias_two", "alias_three"];
const factorPolicyRanking = [
  ...independentFactors.flatMap((factor) => policies.map((policy_id) => {
    const selected = factor === "factor_alpha" && policy_id === "score_liquidity_rank";
    return {
      factor,
      policy_id,
      comparison_status: "available",
      selected,
      absolute_guardrail_pass: true,
      selection_eligible: true,
      selection_status: "eligible",
      selection_score: selected ? 91.2 : 50,
      min_target_effective_names: 10,
      current_target_effective_names: 10,
      max_target_hhi: 0.1,
      current_target_hhi: 0.1,
      max_target_weight: 0.01,
      current_target_max_weight: 0.01,
      guardrail_historical_effective_names: true,
      guardrail_current_effective_names: true,
      guardrail_historical_target_hhi: true,
      guardrail_current_target_hhi: true,
      guardrail_historical_target_weight: true,
      guardrail_current_target_weight: true,
      exclusion_reason_codes: [],
      exclusion_reasons: [],
    };
  })),
  ...aliasFactors.flatMap((factor) => policies.map((policy_id) => ({
    factor,
    policy_id,
    comparison_status: "duplicate_alias",
    selected: false,
    absolute_guardrail_pass: false,
    selection_eligible: false,
    selection_status: "data_excluded",
    selection_score: null,
    min_target_effective_names: 10,
    current_target_effective_names: 10,
    max_target_hhi: 0.1,
    current_target_hhi: 0.1,
    max_target_weight: 0.01,
    current_target_max_weight: 0.01,
    guardrail_historical_effective_names: true,
    guardrail_current_effective_names: true,
    guardrail_historical_target_hhi: true,
    guardrail_current_target_hhi: true,
    guardrail_historical_target_weight: true,
    guardrail_current_target_weight: true,
    exclusion_reason_codes: ["duplicate_alias"],
    exclusion_reasons: [{ code: "duplicate_alias", detail: "compatibility alias" }],
  }))),
];

const payload = {
  schemaVersion: 4,
  resultKey: first.resultKey,
  resultIdentity: first.identity,
  generatedAtUtc: "2026-07-11T00:00:00Z",
  selectedFactor: "factor_alpha",
  selectedWeightingPolicy: "score_liquidity_rank",
  selectedReason: "Python selected this joint factor-policy pair.",
  selectionDecision: {
    method: "joint_factor_policy",
    guardrailProfile: fixtureGuardrailProfile,
  },
  gridAccounting: {
    version: 1,
    independentFactorCount: 61,
    policyCount: 4,
    expectedIndependentPairCount: 244,
    evaluatedIndependentPairCount: 244,
    availableIndependentPairCount: 244,
    excludedIndependentPairCount: 0,
    missingIndependentPairCount: 0,
    commonComparableFactorCount: 61,
    diagnosticAliasFactorCount: 3,
    diagnosticAliasPairCount: 12,
    exclusionReasonCounts: {},
  },
  factorPolicyRanking,
  policyDiagnostics: [],
  weightingPolicyRegistry: {
    registryVersion: "weighting-policy-registry-v2",
    policies: Object.fromEntries(policies.map((policyId) => [policyId, {
        version: "1",
        implementationId: `${policyId}_v1`,
        label: policyId,
        formula: "python-owned",
      }])),
  },
  currentResearchTarget: {
    factor: "factor_alpha",
    weightingPolicyId: "score_liquidity_rank",
    weightingPolicyVersion: "1",
    asOf: "2024-05-31",
    signalDate: "2024-05-31",
    selectedSecurityCount: 10,
    eligibleSecurityCount: 10,
    cashWeight: 0.9,
    weights: Array.from({ length: 10 }, (_value, index) => ({
      rank: index + 1,
      symbol: `AAA${index + 1}`,
      factorScore: 1 - index / 100,
      maxWeight: 0.1,
      weight: 0.01,
    })),
    concentration: {
      investedWeight: 0.1,
      cashWeight: 0.9,
      riskySleeveHhi: 0.1,
      effectiveNames: 10,
      top1Weight: 0.01,
      top5Weight: 0.05,
      maxWeight: 0.01,
    },
  },
  currentTransition: { oneWayTurnover: 0.1, modeledCostFraction: 0.0001 },
  selectionMethod: { name: "joint_factor_policy_absolute_guardrails" },
  performance: { weightingPolicyId: "score_liquidity_rank", factorCurves: {} },
  factorDefinitions: [],
  researchInputs: fixtureResearchInputs,
  researchScope: {},
  config: {
    max_weight: 0.1,
    top_n: 20,
    selection_min_effective_names: 10,
    selection_max_target_hhi: 0.15,
    selection_max_target_weight: 0.15,
  },
  meta: { policyFactorRunCount: 256 },
  priceSources,
  sourceHealth,
  data: {
    mode: "live_market",
    synthetic: false,
    sourceLabel: "actual-provider-fixture",
    provider: "actual-provider-fixture",
    priceBasis: "provider_adjusted_close",
    volumeBasis: "raw_close_x_raw_volume",
    rawCloseProxySymbolCount: 0,
    requestedThrough: "2024-05-31",
    asOf: "2024-05-31",
    requestedCandidateCount: 2_865,
    providerReturnedCandidateCount: 2_861,
    analyzedSecurityCount: 2_861,
    analyzedSymbols: fixtureAnalyzedSymbols,
    inputSha256: fixtureInputSha256,
  },
};
const summary = {
  schemaVersion: 4,
  resultKey: first.resultKey,
  resultIdentity: first.identity,
  dataAsOf: "2024-05-31",
  dataMode: "live_market",
  synthetic: false,
  analyzedSecurityCount: 2_861,
  selectedFactor: "factor_alpha",
  selectedWeightingPolicy: "score_liquidity_rank",
  currentResearchTarget: payload.currentResearchTarget,
  portfolioSize: 10,
  cashWeight: 0.9,
  maxWeight: 0.1,
  weights: payload.currentResearchTarget.weights,
  concentration: payload.currentResearchTarget.concentration,
};

const cachedApiResult = await api.resolveLocalApiResult(
  { statusCode: 200, body: payload },
  0,
);
assert.equal(
  cachedApiResult.resultKey,
  payload.resultKey,
  "a cached local API POST must return the canonical result without polling",
);
assert.equal(cachedApiResult.selectedWeightingPolicy, payload.selectedWeightingPolicy);
const completedStatusBytes = new TextEncoder().encode(JSON.stringify({
  resultKey: first.resultKey,
  status: "complete",
  statusUrl: `/api/runs/${first.resultKey}`,
  result: payload,
}));
mockResponse = {
  ok: true,
  status: 200,
  arrayBuffer: async () => completedStatusBytes.buffer,
};
const polledApiResult = await api.resolveLocalApiResult({
    statusCode: 202,
    body: { resultKey: first.resultKey, statusUrl: `/api/runs/${first.resultKey}` },
  }, 0);
assert.equal(
  polledApiResult.resultKey,
  payload.resultKey,
  "a queued local API POST must poll its status URL until the canonical result completes",
);
assert.equal(polledApiResult.selectedWeightingPolicy, payload.selectedWeightingPolicy);

assert.equal(
  await api.validateResult(first, payload, summary),
  payload.factorPolicyRanking.find((row) => row.selected),
);
await assert.rejects(
  () => api.validateResult(first, payload, {
    ...summary,
    resultIdentity: { ...summary.resultIdentity, resultKey: second.resultKey },
  }),
  /summary resultKey/,
  "summary/detail identity mismatch must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, payload, { ...summary, weights: [], cashWeight: 1 }),
  /weights가 다릅니다/,
  "summary/detail allocation mismatch must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    currentResearchTarget: {
      ...payload.currentResearchTarget,
      cashWeight: 1.25,
      weights: payload.currentResearchTarget.weights.map((row, index) => (
        index === 0 ? { ...row, weight: -0.25 } : row
      )),
    },
  }, summary),
  /보유 행이 잘못되었습니다/,
  "invalid Python-owned allocation must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    gridAccounting: { ...payload.gridAccounting, exclusionReasonCounts: { impossible: 1 } },
  }, summary),
  /exclusionReasonCounts/,
  "grid exclusion reason accounting must reconcile to exact row reasons",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    factorPolicyRanking: payload.factorPolicyRanking.map((row) => (
      row.selected ? { ...row, min_target_effective_names: 9 } : row
    )),
  }, summary),
  /guardrail_historical_effective_names/,
  "the browser must recompute historical worst-case concentration guardrails",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    factorPolicyRanking: payload.factorPolicyRanking.map((row) => (
      !row.selected && row.factor === "factor_01" && row.policy_id === "equal_weight"
        ? { ...row, current_target_hhi: 0.2 }
        : row
    )),
  }, summary),
  /guardrail_current_target_hhi/,
  "a mutated concentration metric on a nonselected row must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    factorPolicyRanking: payload.factorPolicyRanking.map((row) => (
      row.selected ? { ...row, absolute_guardrail_pass: false } : row
    )),
  }, summary),
  /pass\/eligible\/selected/,
  "the selected row must explicitly pass and remain eligible and selected",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        rules: fixtureGuardrailProfile.rules.slice(1),
      },
    },
  }, summary),
  /guardrailProfile/,
  "removing a guardrail rule must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        rules: [
          ...fixtureGuardrailProfile.rules,
          {
            id: "unexpected_rule",
            metric: "median_target_hhi",
            operator: "<=",
            threshold: 0.15,
            unit: "fraction",
          },
        ],
      },
    },
  }, summary),
  /guardrailProfile/,
  "adding a guardrail rule must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        rules: fixtureGuardrailProfile.rules.map((rule) => (
          rule.id === "minimum_sharpe" ? { ...rule, threshold: 0.01 } : rule
        )),
      },
    },
  }, summary),
  /guardrailProfile/,
  "a guardrail threshold not bound to researchInputs must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        requiredContracts: {
          ...fixtureGuardrailProfile.requiredContracts,
          completeExecutionCoverage: false,
        },
      },
    },
  }, summary),
  /guardrailProfile/,
  "mutating a required guardrail contract must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        extremeEventAction: "warn",
      },
    },
  }, summary),
  /guardrailProfile/,
  "the extreme-event action must remain bound to researchInputs",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    selectionDecision: {
      ...payload.selectionDecision,
      guardrailProfile: {
        ...fixtureGuardrailProfile,
        extremeEventPenaltyPoints: 19,
      },
    },
  }, summary),
  /guardrailProfile/,
  "the extreme-event penalty must remain bound to researchInputs",
);
await assert.rejects(
  () => api.validateResult(first, { ...payload, priceSources: [] }, summary),
  /priceSources가 비어/,
  "an actual-market result without per-symbol price provenance must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, { ...payload, sourceHealth: [] }, summary),
  /sourceHealth가 비어/,
  "an actual-market result without acquisition health provenance must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    priceSources: payload.priceSources.map((row, index) => (
      index === 0 ? { ...row, price_source: "silently-mutated-provider" } : row
    )),
  }, summary),
  /priceSources RFC 8785 JCS SHA-256/,
  "editing a valid priceSources row without updating its bound hash must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    sourceHealth: payload.sourceHealth.map((row, index) => (
      index === 0 ? { ...row, status: "silently-mutated-status" } : row
    )),
  }, summary),
  /sourceHealth RFC 8785 JCS SHA-256/,
  "editing a valid sourceHealth row without updating its bound hash must fail closed",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    data: { ...payload.data, priceBasis: "silently-mutated-price-contract" },
  }, summary),
  /marketSnapshot이 detail data와 다릅니다/,
  "market basis semantics must remain bound to result identity",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    data: {
      ...payload.data,
      inputSha256: { ...payload.data.inputSha256, unexpected: "f".repeat(64) },
    },
  }, summary),
  /provenance 입력 해시/,
  "the browser must reject extra live input-hash keys",
);
await assert.rejects(
  () => api.validateResult(first, {
    ...payload,
    data: {
      ...payload.data,
      analyzedSymbols: [
        payload.data.analyzedSymbols[1],
        payload.data.analyzedSymbols[0],
        ...payload.data.analyzedSymbols.slice(2),
      ],
    },
  }, summary),
  /marketSnapshot이 detail data와 다릅니다/,
  "ordered analyzed symbols must match candidateSymbolsSha256",
);

assert.match(source, /data\/grid\/v1\/manifest\.json/);
assert.match(source, /history\.pushState/);
assert.match(source, /popstate/);
assert.match(source, /factorPolicyRanking/);
assert.match(source, /currentResearchTarget/);
assert.match(source, /weightingPolicyRegistry/);
assert.match(source, /renderRiskDiagnostics/);
assert.match(source, /contributionDiagnostics/);
assert.match(source, /guardrail_breaches/);
assert.match(source, /maxExactSingleSessionSecurityContribution/);
assert.match(source, /topLeaveOneSecurity/);
assert.match(source, /isSelectedPair/);
assert.match(source, /row\.max_abs_security_day_contribution/);
assert.match(source, /선택 조합에서만 상세 이벤트 제공/);
assert.match(source, /crypto\.subtle\.digest/);
assert.match(source, /byte count가 manifest와 다릅니다/);
assert.match(source, /POST/);
assert.match(source, /\/api\/runs/);
assert.match(source, /queued/);
assert.match(source, /running/);
assert.match(source, /gridAccounting\.exclusionReasonCounts/);
assert.doesNotMatch(source, /weightingPolicyComparison|factorRanking|score_size_liquidity|modelPortfolio/);
assert.doesNotMatch(source, /calculateComposite|calculateWeights|constructTargetAllocation/);

console.log("PASS static web manifest, URL, v4 identity, and Python-owned result contract checks");
