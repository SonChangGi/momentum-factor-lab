import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import vm from "node:vm";

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");
const context = vm.createContext({
  console,
  crypto: webcrypto,
  setTimeout,
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
});
vm.runInContext(source, context, { filename: "momentum_factor_lab/web/dashboard.js" });
const api = context.__MFL_WEB_TESTS__;
assert(api, "local API browser helpers must be exported without a DOM");

const explicitPayloadPath = process.env.MFL_TEST_PAYLOAD;
const previewFixtureRoot = existsSync(
  "outputs/final-evidence-preview-20260713/site/data/grid/v1/manifest.json",
)
  ? "outputs/final-evidence-preview-20260713/site"
  : existsSync("outputs/final-actual-preview-20260713/site/data/grid/v1/manifest.json")
    ? "outputs/final-actual-preview-20260713/site"
    : null;
const fixtureSiteRoot = process.env.MFL_TEST_SITE_ROOT
  || (explicitPayloadPath ? dirname(dirname(explicitPayloadPath)) : null)
  || previewFixtureRoot
  || "docs";

assert.match(html, /id="research-controls" class="advanced-canonical-inputs canonical-input-details"/);
assert.match(html, /class="core-research-inputs"/);
assert.match(html, /id="advanced-research-inputs" class="advanced-research-inputs"/);
assert.match(html, /공개 preset에 없는 조건은 로컬 Python API가 필요합니다/);
assert.match(html, /id="result-source"/);
assert.match(html, /id="result-key"/);
assert.match(css, /span\[data-source="static_grid"\]/);
assert.match(css, /span\[data-source="local_api"\]/);
assert.equal(api.resultSourceLabel("static_grid"), "검증된 정적 preset");
assert.equal(api.resultSourceLabel("local_api"), "로컬 API 계산 결과");
assert.equal(api.resultSourceLabel(null), "결과 없음");

const proxyIds = new Set([
  "lookback-months-select",
  "topn-input",
  "max-weight-input",
  "rebalance-select",
  "transaction-cost-input",
  "slippage-input",
]);
assert(
  api.INPUT_FIELDS.every((field) => !proxyIds.has(field.id)),
  "canonical ResearchInputs must never reuse browser proxy controls",
);
for (const id of proxyIds) {
  assert(!html.includes(`id="${id}"`), `removed browser proxy control must not return: ${id}`);
}

const manifest = api.validateManifest(JSON.parse(
  readFileSync(join(fixtureSiteRoot, "data/grid/v1/manifest.json"), "utf8"),
));
const defaultEntry = manifest.entries.find(
  (entry) => entry.resultKey === manifest.defaultResultKey,
);
assert(defaultEntry, "manifest default entry is required");
for (const field of api.INPUT_FIELDS.filter((item) => item.kind !== "string")) {
  const tag = html.match(new RegExp(`<input[^>]*id="${field.id}"[^>]*>`))?.[0];
  assert(tag, `missing numeric input element: ${field.id}`);
  const value = Number(api.serializeInputValue(field, defaultEntry.normalizedInputs[field.key]));
  const min = Number(tag.match(/\bmin="([^"]+)"/)?.[1] ?? 0);
  const maxText = tag.match(/\bmax="([^"]+)"/)?.[1];
  const stepText = tag.match(/\bstep="([^"]+)"/)?.[1];
  assert(Number.isFinite(value), `${field.id} default must serialize to a finite number`);
  assert(value >= min, `${field.id} default must satisfy min`);
  if (maxText !== undefined) assert(value <= Number(maxText), `${field.id} default must satisfy max`);
  if (stepText && stepText !== "any") {
    const step = Number(stepText);
    const offset = (value - min) / step;
    assert(
      Math.abs(offset - Math.round(offset)) < 1e-7,
      `${field.id} default ${value} must satisfy native step ${stepText} from min ${min}`,
    );
  }
}
assert.equal(api.serializeInputValue(
  api.INPUT_FIELDS.find((field) => field.key === "max_extreme_daily_return"),
  0.8,
), "80");
const unsupportedInputs = structuredClone(defaultEntry.normalizedInputs);
unsupportedInputs.top_n = 21;
assert.equal(api.resolveExactEntry(manifest, unsupportedInputs), null);
const prepared = api.localApiRequestFromStaticState(manifest, unsupportedInputs);
assert.equal(prepared.baseEntry.resultKey, manifest.defaultResultKey);
assert.equal(prepared.requestedInputs.top_n, 21);
const researchInputs = api.researchInputsFromNormalizedInputs(prepared.requestedInputs);
assert.equal(researchInputs.version, "research-inputs-v1");
assert.equal(researchInputs.topN, 21);
assert.equal(researchInputs.evaluationWindowDays, researchInputs.evaluationYears * 252);
assert.equal(Object.keys(researchInputs).length, 28);

function jsonResponse(value, status = 200) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  return {
    ok: status >= 200 && status < 300,
    status,
    arrayBuffer: async () => Uint8Array.from(bytes).buffer,
  };
}

let observedPost = null;
const resultKey = "a".repeat(64);
const submission = await api.fetchLocalApiJson("/api/runs", {
  method: "POST",
  body: researchInputs,
  fetchImpl: async (url, options) => {
    observedPost = { url: String(url), options };
    return jsonResponse({
      resultKey,
      status: "queued",
      statusUrl: `/api/runs/${resultKey}`,
    }, 202);
  },
});
assert.equal(submission.statusCode, 202);
assert.equal(observedPost.url, "http://127.0.0.1:8765/api/runs");
assert.equal(observedPost.options.method, "POST");
assert.deepEqual(
  JSON.parse(observedPost.options.body),
  JSON.parse(JSON.stringify(researchInputs)),
);
assert.equal(
  observedPost.options.body,
  api.canonicalString(researchInputs),
  "the loopback POST body must use the canonical complete ResearchInputs JSON",
);

const statuses = [
  { resultKey, status: "queued", statusUrl: `/api/runs/${resultKey}` },
  { resultKey, status: "running", statusUrl: `/api/runs/${resultKey}` },
  {
    resultKey,
    status: "complete",
    statusUrl: `/api/runs/${resultKey}`,
    result: { schemaVersion: 4, resultKey },
  },
];
const polledUrls = [];
const observedStatuses = [];
const resolved = await api.resolveLocalApiResult(submission, 7, {
  fetchStatus: async (url) => {
    polledUrls.push(url);
    return { statusCode: 200, body: statuses.shift() };
  },
  wait: async () => {},
  isCurrent: () => true,
  onStatus: (status, key) => observedStatuses.push([status, key]),
});
assert.deepEqual(resolved, { schemaVersion: 4, resultKey });
assert.equal(polledUrls.length, 3);
assert.deepEqual(observedStatuses, [
  ["queued", resultKey],
  ["running", resultKey],
]);

assert.deepEqual(
  await api.resolveLocalApiResult({ statusCode: 200, body: { cached: true } }, 8),
  { cached: true },
  "cached 200 local results must not enter polling",
);
await assert.rejects(
  api.resolveLocalApiResult({
    statusCode: 202,
    body: { resultKey, statusUrl: `/api/runs/${resultKey}` },
  }, 9, {
    fetchStatus: async () => ({
      statusCode: 200,
      body: { resultKey, status: "failed", error: { message: "fixture failure" } },
    }),
    wait: async () => {},
    isCurrent: () => true,
    onStatus: () => {},
  }),
  /로컬 Python 분석 실패: fixture failure/,
);

const payloadPath = explicitPayloadPath || join(fixtureSiteRoot, "data/dashboard.json");
const actualPayload = JSON.parse(readFileSync(payloadPath, "utf8"));
const comparisonFactor = Object.keys(actualPayload.factorPortfolios).find((factor) => (
  factor !== actualPayload.selectedFactor
  && actualPayload.factorPortfolios[factor]?.status === "available"
  && actualPayload.factorPortfolios[factor]?.weights?.length > 0
));
assert(comparisonFactor, "fixture needs a non-selected Python factor portfolio");
const comparisonPortfolio = api.portfolioHoldingsFromPayload(actualPayload, comparisonFactor);
assert.equal(
  comparisonPortfolio.weighted.length,
  actualPayload.factorPortfolios[comparisonFactor].weights.length,
);
assert.equal(
  comparisonPortfolio.weighted[0].display_weight,
  actualPayload.factorPortfolios[comparisonFactor].weights[0].weight,
  "comparison chart must render Python factorPortfolios weights without browser recomputation",
);
assert.equal(comparisonPortfolio.weightingPolicyId, actualPayload.selectedWeightingPolicy);
const localEntry = {
  resultKey: actualPayload.resultKey,
  normalizedInputs: actualPayload.resultIdentity.keyParts.normalizedInputs,
  identity: actualPayload.resultIdentity,
};
await api.validateIdentityDigest(localEntry.identity, "local API fixture");
await api.validateResult(localEntry, actualPayload, null, {
  source: "local_api",
  expectedResearchInputs: actualPayload.researchInputs,
});

const shareSearch = api.searchForRequest(
  prepared.baseEntry.resultKey,
  prepared.requestedInputs,
  prepared.baseEntry.presetId,
);
const restored = api.requestFromSearch(manifest, shareSearch);
assert.equal(restored.entry, null);
assert.equal(restored.requestedInputs.top_n, 21);
assert.equal(restored.baseEntry.resultKey, prepared.baseEntry.resultKey);
assert.match(source, /loadLocalApiResult\(apiRequest\.requestedInputs, apiRequest\.baseEntry/);
assert.match(source, /setResultSource\(source, entry\.resultKey\)/);

console.log(
  "PASS official Python research form, local API POST/202 polling, source badge, validation, and shareable replay contracts",
);
