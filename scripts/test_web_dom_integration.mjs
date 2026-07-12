import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const manifest = JSON.parse(readFileSync("docs/data/grid/v1/manifest.json", "utf8"));
const defaultEntry = manifest.entries.find(
  (entry) => entry.resultKey === manifest.defaultResultKey,
);
assert(defaultEntry, "published manifest must contain its default entry");
const defaultPayload = JSON.parse(readFileSync(
  `docs/data/grid/v1/${defaultEntry.detail.path}`,
  "utf8",
));

const helperContext = vm.createContext({
  console,
  crypto: webcrypto,
  fetch: async () => {
    throw new Error("helper context must not fetch");
  },
  setTimeout,
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
});
vm.runInContext(source, helperContext, {
  filename: "momentum_factor_lab/web/dashboard.js",
});
const helperApi = helperContext.__MFL_WEB_TESTS__;
assert(helperApi, "web helper API must be available");

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(...values) {
    values.forEach((value) => this.values.add(value));
  }

  remove(...values) {
    values.forEach((value) => this.values.delete(value));
  }

  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : Boolean(force);
    if (enabled) this.values.add(value);
    else this.values.delete(value);
    return enabled;
  }
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.dataset = {};
    this.classList = new FakeClassList();
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }

  dispatch(type, event = {}) {
    const payload = { target: this, ...event };
    for (const listener of this.listeners.get(type) || []) listener(payload);
  }
}

const htmlIds = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
const elements = new Map(htmlIds.map((id) => [id, new FakeElement(id)]));
const compoundElements = new Map();
const body = new FakeElement("body");
const documentElement = new FakeElement("html");
const document = {
  body,
  documentElement,
  querySelector(selector) {
    if (!selector.startsWith("#")) return null;
    const id = selector.slice(1).split(/[ .:[>+~]/, 1)[0];
    if (!elements.has(id)) return null;
    if (selector === `#${id}`) return elements.get(id);
    if (!compoundElements.has(selector)) {
      compoundElements.set(selector, new FakeElement(selector));
    }
    return compoundElements.get(selector);
  },
  querySelectorAll(selector) {
    if (selector === "[data-pair]") return [];
    return [];
  },
};

const pageUrl = new URL("https://sonchanggi.github.io/momentum-factor-lab/index.html");
const location = {
  href: pageUrl.href,
  pathname: pageUrl.pathname,
  search: "",
  hash: "",
};
function applyLocation(next) {
  const resolved = new URL(next, location.href);
  location.href = resolved.href;
  location.pathname = resolved.pathname;
  location.search = resolved.search;
  location.hash = resolved.hash;
}
const historyCalls = [];
const history = {
  pushState(state, _title, next) {
    historyCalls.push({ mode: "push", state, next });
    applyLocation(next);
  },
  replaceState(state, _title, next) {
    historyCalls.push({ mode: "replace", state, next });
    applyLocation(next);
  },
};
const windowListeners = new Map();
const window = {
  location,
  matchMedia: () => ({ matches: false }),
  addEventListener(type, listener) {
    windowListeners.set(type, listener);
  },
};
const storage = new Map();
const localStorage = {
  getItem(key) {
    return storage.get(key) ?? null;
  },
  setItem(key, value) {
    storage.set(key, String(value));
  },
};

function byteResponse(bytes, status = 200) {
  const copied = Uint8Array.from(bytes);
  return {
    ok: status >= 200 && status < 300,
    status,
    arrayBuffer: async () => copied.buffer,
  };
}
function jsonResponse(value, status = 200) {
  return byteResponse(new TextEncoder().encode(JSON.stringify(value)), status);
}

function canonicalDynamicPayload(researchInputs) {
  const payload = JSON.parse(JSON.stringify(defaultPayload));
  const normalizedInputs = JSON.parse(JSON.stringify(defaultEntry.normalizedInputs));
  const publicToNormalized = {
    rebalanceFrequency: "rebalance_frequency",
    evaluationWindowDays: "evaluation_window_days",
    topN: "top_n",
    maxWeight: "max_weight",
    transactionCostBps: "transaction_cost_bps",
    slippageBps: "slippage_bps",
    minHistoryDays: "min_history_days",
    minPrice: "min_price",
    minAvgDollarVolume: "min_avg_dollar_volume",
    minAvgVolume: "min_avg_volume",
    liquidityLookbackDays: "liquidity_lookback_days",
    minLiquidityObservations: "min_liquidity_observations",
    maxPriceMissingRatio: "max_price_missing_ratio",
    maxVolumeMissingRatio: "max_volume_missing_ratio",
    maxExtremeDailyReturn: "max_extreme_daily_return",
    selectionMinSharpe: "selection_min_sharpe",
    selectionMaxDrawdown: "selection_max_drawdown",
    selectionMaxAnnualizedCostDrag: "selection_max_annualized_cost_drag",
    selectionMinEffectiveNames: "selection_min_effective_names",
    selectionMaxTargetHhi: "selection_max_target_hhi",
    selectionMaxTargetWeight: "selection_max_target_weight",
    selectionMaxAbsSecurityDayContribution: "selection_max_abs_security_day_contribution",
    selectionMaxSecurityAbsoluteContributionShare:
      "selection_max_security_absolute_contribution_share",
    selectionMaxLeaveOneSecurityCagrDelta:
      "selection_max_leave_one_security_cagr_delta",
    selectionExtremeEventAction: "selection_extreme_event_action",
    selectionExtremeEventPenaltyPoints: "selection_extreme_event_penalty_points",
  };
  for (const [publicKey, normalizedKey] of Object.entries(publicToNormalized)) {
    normalizedInputs[normalizedKey] = researchInputs[publicKey];
  }
  normalizedInputs.min_evaluation_observations = Math.max(
    252,
    normalizedInputs.evaluation_window_days - 252,
  );
  normalizedInputs.min_daily_risk_observations =
    normalizedInputs.min_evaluation_observations;
  const keyParts = JSON.parse(JSON.stringify(payload.resultIdentity.keyParts));
  keyParts.normalizedInputs = normalizedInputs;
  const canonicalKeyPartsJson = helperApi.canonicalString(keyParts);
  const resultKey = createHash("sha256")
    .update(canonicalKeyPartsJson)
    .digest("hex");
  const identity = {
    identityVersion: "momentum-result-identity-v1",
    resultKey,
    keyParts,
    canonicalKeyPartsJson,
  };
  payload.resultKey = resultKey;
  payload.resultIdentity = identity;
  payload.researchInputs = researchInputs;
  payload.config.top_n = researchInputs.topN;
  return payload;
}

let dynamicPayload = null;
let postCount = 0;
async function fetch(url, options = {}) {
  const parsed = new URL(String(url));
  if (parsed.origin === "http://127.0.0.1:8765") {
    if (options.method === "POST" && parsed.pathname === "/api/runs") {
      postCount += 1;
      const researchInputs = JSON.parse(options.body);
      dynamicPayload = canonicalDynamicPayload(researchInputs);
      return jsonResponse({
        resultKey: dynamicPayload.resultKey,
        status: "queued",
        statusUrl: `/api/runs/${dynamicPayload.resultKey}`,
      }, 202);
    }
    if (options.method === "GET" && parsed.pathname.startsWith("/api/runs/")) {
      assert(dynamicPayload, "status polling must follow a POST");
      return jsonResponse({
        resultKey: dynamicPayload.resultKey,
        status: "complete",
        statusUrl: `/api/runs/${dynamicPayload.resultKey}`,
        result: dynamicPayload,
      });
    }
    return jsonResponse({ error: { message: "unexpected local API request" } }, 404);
  }

  const prefix = "/momentum-factor-lab/";
  assert(parsed.pathname.startsWith(prefix), `unexpected static URL: ${parsed.href}`);
  const relative = parsed.pathname.slice(prefix.length);
  return byteResponse(readFileSync(`docs/${relative}`));
}

const context = vm.createContext({
  console,
  crypto: webcrypto,
  document,
  fetch,
  history,
  localStorage,
  setTimeout: (callback) => {
    callback();
    return 0;
  },
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
  window,
});
vm.runInContext(source, context, {
  filename: "momentum_factor_lab/web/dashboard.js",
});

async function waitFor(predicate, label) {
  const deadline = Date.now() + 5_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(`timed out waiting for ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

await waitFor(
  () => elements.get("result-source").textContent === "정적 사전 계산 결과",
  "initial static rendering",
);
assert.equal(elements.get("result-key").textContent, defaultEntry.resultKey);
assert.equal(elements.get("decision-factor").textContent, defaultPayload.selectedFactor);
assert.match(elements.get("winner-reason").textContent, /Selected the joint factor-policy pair/);
assert.match(elements.get("winner-metrics").innerHTML, /CAGR/);
assert.match(elements.get("winner-metrics").innerHTML, /회전율/);
assert.match(compoundElements.get("#allocation-table tbody").innerHTML, /weight-cell/);
assert.match(elements.get("allocation-contract").innerHTML, /현재 추정 비용/);
assert.notEqual(elements.get("compact-cash").textContent, "—");

elements.get("input-top-n").value = "21";
elements.get("research-input-form").dispatch("submit", {
  preventDefault() {},
});
await waitFor(
  () => elements.get("result-source").textContent === "로컬 API 계산 결과",
  "local API rendering",
);
assert.equal(postCount, 1);
assert.equal(elements.get("result-key").textContent, dynamicPayload.resultKey);
assert.match(location.search, /top_n=21/);
assert.match(elements.get("winner-metrics").innerHTML, /CAGR/);
assert.match(compoundElements.get("#allocation-table tbody").innerHTML, /weight-cell/);
assert(historyCalls.some((call) => call.mode === "replace"));

const popstate = windowListeners.get("popstate");
assert.equal(typeof popstate, "function");
popstate();
await waitFor(() => postCount === 2, "shared URL popstate replay");
await waitFor(
  () => elements.get("result-source").textContent === "로컬 API 계산 결과",
  "shared URL result rendering",
);
assert.match(location.search, /top_n=21/);

console.log(
  "PASS DOM form, static render, local API 202 polling, full render, history, and popstate contracts",
);
