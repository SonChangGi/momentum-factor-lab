import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import vm from "node:vm";

const root = process.cwd();
const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
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
assert(api, "browser trust-boundary helpers must be exported without a DOM");

const explicitPayloadPath = process.env.MFL_TEST_PAYLOAD;
const previewFixtureRoot = existsSync(
  "outputs/final-evidence-preview-20260713/site/data/grid/v1/manifest.json",
)
  ? "outputs/final-evidence-preview-20260713/site"
  : existsSync("outputs/final-actual-preview-20260713/site/data/grid/v1/manifest.json")
    ? "outputs/final-actual-preview-20260713/site"
    : null;
const publicationFixtureRoot = process.env.MFL_TEST_SITE_ROOT
  || (explicitPayloadPath ? dirname(dirname(explicitPayloadPath)) : null)
  || previewFixtureRoot
  || "docs";

assert.doesNotMatch(
  source,
  /fetch\(['"]data\/dashboard\.json['"]\)/,
  "the browser must not bypass the bounded manifest through the default alias",
);
assert.match(source, /const MANIFEST_URL = 'data\/grid\/v1\/manifest\.json'/);
assert.match(source, /window\.addEventListener\('popstate', \(\) => loadFromLocation\(\)\)/);

const htmlIds = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
for (const id of [
  "run-select",
  "research-controls",
  "research-input-form",
  "result-source",
  "result-key",
  "input-status",
  "reset-default-inputs",
]) {
  assert(htmlIds.has(id), `missing static/local result control: ${id}`);
}
for (const field of api.INPUT_FIELDS) {
  assert(htmlIds.has(field.id), `missing canonical ResearchInputs control: ${field.id}`);
}

const publishedManifest = api.validateManifest(JSON.parse(
  readFileSync(`${publicationFixtureRoot}/data/grid/v1/manifest.json`, "utf8"),
));
assert.equal(publishedManifest.entryCount, 3, "the publication fixture must expose three presets");
assert.equal(new Set(publishedManifest.entries.map((entry) => entry.presetId)).size, 3);

for (const entry of publishedManifest.entries) {
  await api.validateIdentityDigest(entry.identity, entry.presetId);
  const detail = JSON.parse(readFileSync(`${publicationFixtureRoot}/data/grid/v1/${entry.detail.path}`, "utf8"));
  const summary = JSON.parse(readFileSync(`${publicationFixtureRoot}/data/grid/v1/${entry.summary.path}`, "utf8"));
  await api.validateResult(entry, detail, summary);
  const roundTripSearch = api.searchForRequest(
    entry.resultKey,
    entry.normalizedInputs,
    entry.presetId,
  );
  const roundTrip = api.requestFromSearch(publishedManifest, roundTripSearch);
  assert.equal(roundTrip.error, null);
  assert.equal(roundTrip.entry.resultKey, entry.resultKey);
  assert.equal(
    api.canonicalString(roundTrip.requestedInputs),
    api.canonicalString(entry.normalizedInputs),
  );
}

const second = publishedManifest.entries[1];
const rotatedSearch = api.searchForRequest(
  "f".repeat(64),
  second.normalizedInputs,
  second.presetId,
);
const recovered = api.requestFromSearch(publishedManifest, rotatedSearch);
assert.equal(recovered.recoveredFromRotatedResult, true);
assert.equal(recovered.baseEntry.resultKey, second.resultKey);
assert.equal(recovered.entry.resultKey, second.resultKey);

const unsupportedInputs = { ...second.normalizedInputs, top_n: 21 };
const unsupported = api.requestFromSearch(
  publishedManifest,
  api.searchForRequest(second.resultKey, unsupportedInputs, second.presetId),
);
assert.equal(unsupported.entry, null, "unsupported inputs must never choose a nearest preset");
assert.match(unsupported.error, /loopback Python API/);

const badManifestParity = structuredClone(publishedManifest);
badManifestParity.entries[0].normalizedInputs.top_n += 1;
assert.throws(() => api.validateManifest(badManifestParity), /normalizedInputs가 identity와 다릅니다/);
const badManifestReference = structuredClone(publishedManifest);
badManifestReference.entries[0].detail.sha256 = "0".repeat(64);
assert.equal(api.validateManifest(badManifestReference), badManifestReference);
await assert.rejects(
  api.validateIdentityDigest(
    { ...publishedManifest.entries[0].identity, resultKey: "0".repeat(64) },
    "tampered manifest identity",
  ),
  /canonical keyParts SHA-256과 다릅니다/,
);

const payloadPath = explicitPayloadPath || join(publicationFixtureRoot, "data/dashboard.json");
const siteRoot = resolve(publicationFixtureRoot);
const manifestPath = join(siteRoot, "data/grid/v1/manifest.json");
const actualManifest = api.validateManifest(JSON.parse(readFileSync(manifestPath, "utf8")));
const actualEntry = actualManifest.entries.find(
  (entry) => entry.resultKey === actualManifest.defaultResultKey,
);
assert(actualEntry, "actual preview manifest must contain its default entry");

function responseFromBytes(bytes, status = 200) {
  const copy = Uint8Array.from(bytes);
  return {
    ok: status >= 200 && status < 300,
    status,
    arrayBuffer: async () => copy.buffer,
  };
}

function siteFetch(url) {
  const parsed = new URL(String(url));
  const relative = decodeURIComponent(parsed.pathname.replace(/^\/+/, ""));
  const path = resolve(siteRoot, relative);
  assert(path.startsWith(`${siteRoot}/`) || path === siteRoot, `path escaped site root: ${path}`);
  return Promise.resolve(responseFromBytes(readFileSync(path)));
}

const manifestUrl = "https://example.test/data/grid/v1/manifest.json";
const loadedEntries = [];
for (const entry of actualManifest.entries) {
  const entryData = await api.loadStaticEntryData(entry, {
    manifestUrl,
    pageUrl: "https://example.test/index.html",
    fetchImpl: siteFetch,
  });
  assert.equal(entryData.payload.resultKey, entry.resultKey);
  assert.equal(entryData.summary.resultKey, entry.resultKey);
  assert.equal(
    Object.keys(entryData.payload.__factorHoldingHistorySidecarData?.factors || {}).length,
    64,
    `${entry.presetId} must load all 64 exact factor holding histories`,
  );
  loadedEntries.push(entryData);
}
const loaded = await api.loadStaticEntryData(actualEntry, {
  manifestUrl,
  pageUrl: "https://example.test/index.html",
  fetchImpl: siteFetch,
});
assert.equal(loaded.payload.resultKey, actualEntry.resultKey);
assert.equal(loaded.summary.resultKey, actualEntry.resultKey);
if (loaded.payload.factorHoldingHistorySidecar) {
  assert.equal(
    loaded.payload.__factorHoldingHistorySidecarData?.resultKey,
    actualEntry.resultKey,
    "the selected entry's sidecar must load after detail/summary validation",
  );
}

function tamperingFetch(kind) {
  return async (url) => {
    const parsed = new URL(String(url));
    const relative = decodeURIComponent(parsed.pathname.replace(/^\/+/, ""));
    const bytes = Uint8Array.from(readFileSync(resolve(siteRoot, relative)));
    if (parsed.pathname.includes(`/grid/v1/${kind}/`)) {
      bytes[Math.floor(bytes.length / 2)] ^= 1;
    }
    return responseFromBytes(bytes);
  };
}

await assert.rejects(
  api.loadStaticEntryData(actualEntry, {
    manifestUrl,
    pageUrl: "https://example.test/index.html",
    fetchImpl: tamperingFetch("results"),
  }),
  /detail SHA-256이 manifest와 다릅니다/,
);
await assert.rejects(
  api.loadStaticEntryData(actualEntry, {
    manifestUrl,
    pageUrl: "https://example.test/index.html",
    fetchImpl: tamperingFetch("summaries"),
  }),
  /summary SHA-256이 manifest와 다릅니다/,
);

const tamperedSummary = structuredClone(loaded.summary);
tamperedSummary.selectedFactor = `${tamperedSummary.selectedFactor}-tampered`;
await assert.rejects(
  api.validateResult(actualEntry, loaded.payload, tamperedSummary),
  /summary\/detail 선택 조합이 다릅니다/,
);
const tamperedTarget = structuredClone(loaded.payload);
tamperedTarget.currentResearchTarget.cashWeight = 0.5;
await assert.rejects(
  api.validateResult(actualEntry, tamperedTarget, loaded.summary),
  /비중과 현금의 합이 1이 아닙니다/,
);
const tamperedGrid = structuredClone(loaded.payload);
tamperedGrid.gridAccounting.availableIndependentPairCount += 1;
await assert.rejects(
  api.validateResult(actualEntry, tamperedGrid, loaded.summary),
  /available \+ excluded가 244와 다릅니다/,
);

for (const field of [
  "backtestHeldPortfolio",
  "selectedBacktestHoldingHistory",
  "factorHoldingHistorySidecar",
]) {
  const missingHoldingContract = structuredClone(loaded.payload);
  delete missingHoldingContract[field];
  await assert.rejects(
    api.validateResult(actualEntry, missingHoldingContract, loaded.summary),
    new RegExp(`detail 필드가 없습니다: ${field}`),
  );
}

const mismatchedQqqEndpoint = structuredClone(loaded.payload);
mismatchedQqqEndpoint.performance.benchmarkCurves.QQQ[
  mismatchedQqqEndpoint.performance.benchmarkCurves.QQQ.length - 1
] *= 0.5;
await assert.rejects(
  api.validateResult(actualEntry, mismatchedQqqEndpoint, loaded.summary),
  /QQQ FULL 누적 수익률이 그래프 endpoint와 다릅니다/,
);

const malformedFactorCurve = structuredClone(loaded.payload);
malformedFactorCurve.performance.factorCurves[loaded.payload.selectedFactor][1] = "not-a-number";
await assert.rejects(
  api.validateResult(actualEntry, malformedFactorCurve, loaded.summary),
  /길이\/유한값\/null gap/,
);

const allowedFactorNullGap = structuredClone(loaded.payload);
allowedFactorNullGap.performance.factorCurves[loaded.payload.selectedFactor][1] = null;
await api.validateResult(actualEntry, allowedFactorNullGap, loaded.summary);

const [firstLoadedEntry, secondLoadedEntry] = loadedEntries;
const firstSidecarPayload = structuredClone(firstLoadedEntry.payload);
const secondSidecarPayload = structuredClone(secondLoadedEntry.payload);
delete firstSidecarPayload.__factorHoldingHistorySidecarData;
delete firstSidecarPayload.__factorHoldingHistorySidecarError;
delete secondSidecarPayload.__factorHoldingHistorySidecarData;
delete secondSidecarPayload.__factorHoldingHistorySidecarError;
const sidecarRequests = [];
const sidecarFetch = async (url) => {
  sidecarRequests.push(String(url));
  return siteFetch(url);
};
await api.attachFactorHoldingHistorySidecar(firstSidecarPayload, {
  fetchImpl: sidecarFetch,
  pageUrl: "https://example.test/index.html",
});
await api.attachFactorHoldingHistorySidecar(secondSidecarPayload, {
  fetchImpl: sidecarFetch,
  pageUrl: "https://example.test/index.html",
});
assert.deepEqual(sidecarRequests, [
  new URL(firstSidecarPayload.factorHoldingHistorySidecar.path, "https://example.test/index.html").href,
  new URL(secondSidecarPayload.factorHoldingHistorySidecar.path, "https://example.test/index.html").href,
]);
assert.equal(
  secondSidecarPayload.__factorHoldingHistorySidecarData.resultKey,
  secondSidecarPayload.resultKey,
);
assert.notEqual(
  secondSidecarPayload.__factorHoldingHistorySidecarData.resultKey,
  firstSidecarPayload.__factorHoldingHistorySidecarData.resultKey,
  "changing entries must load and expose the new entry's sidecar, never stale state",
);

function mutatedSidecarFixture(payload, mutate) {
  const copy = structuredClone(payload);
  delete copy.__factorHoldingHistorySidecarData;
  delete copy.__factorHoldingHistorySidecarError;
  const data = structuredClone(firstLoadedEntry.payload.__factorHoldingHistorySidecarData);
  mutate(data);
  const bytes = new TextEncoder().encode(api.canonicalString(data));
  copy.factorHoldingHistorySidecar.bytes = bytes.byteLength;
  copy.factorHoldingHistorySidecar.sha256 = createHash("sha256").update(bytes).digest("hex");
  return { payload: copy, bytes };
}

const missingFactorSidecar = mutatedSidecarFixture(firstLoadedEntry.payload, (data) => {
  delete data.factors[Object.keys(data.factors)[0]];
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    missingFactorSidecar.payload,
    async () => responseFromBytes(missingFactorSidecar.bytes),
  ),
  /64개 팩터/,
);

const invalidAllocationSidecar = mutatedSidecarFixture(firstLoadedEntry.payload, (data) => {
  const factor = Object.keys(data.factors)[0];
  data.factors[factor].sessions[0].cashWeight = 0.99;
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    invalidAllocationSidecar.payload,
    async () => responseFromBytes(invalidAllocationSidecar.bytes),
  ),
  /배분\/정렬/,
);

const invalidSessionSidecar = mutatedSidecarFixture(firstLoadedEntry.payload, (data) => {
  const factor = Object.keys(data.factors)[0];
  data.factors[factor].sessions.pop();
});
await assert.rejects(
  api.loadV4FactorHoldingHistorySidecar(
    invalidSessionSidecar.payload,
    async () => responseFromBytes(invalidSessionSidecar.bytes),
  ),
  /identity\/session/,
);

console.log(
  "PASS 3-preset selection, URL restoration, artifact identity, performance/holding fail-closed, and semantic sidecar loading",
);
