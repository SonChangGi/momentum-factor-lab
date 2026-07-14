import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import vm from "node:vm";

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.className = "";
    this.title = "";
    this._text = "";
  }

  set textContent(value) {
    this._text = String(value ?? "");
    this.children = [];
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  append(...children) {
    children.forEach((child) => {
      if (typeof child === "string") this.children.push(new FakeText(child));
      else this.children.push(child);
    });
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this._text = "";
    this.children = [];
    this.append(...children);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  findAll(tagName) {
    const target = String(tagName).toUpperCase();
    const descendants = this.children.flatMap((child) => child.findAll?.(target) || []);
    return this.tagName === target ? [this, ...descendants] : descendants;
  }
}

class FakeText extends FakeElement {
  constructor(value) {
    super("#text");
    this._text = String(value);
  }
}

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const payloadPath = process.env.MFL_TEST_PAYLOAD || (
  existsSync("outputs/daily-dashboard/default-detail.json")
    ? "outputs/daily-dashboard/default-detail.json"
    : "docs/data/dashboard.json"
);
const payload = JSON.parse(readFileSync(payloadPath, "utf8"));
const context = vm.createContext({
  console,
  setTimeout,
  TextDecoder,
  TextEncoder,
  URL,
  URLSearchParams,
});
vm.runInContext(source, context, { filename: "momentum_factor_lab/web/dashboard.js" });
context.document = { createElement: (tagName) => new FakeElement(tagName) };

const api = context.__MFL_WEB_TESTS__;
assert(api?.renderPythonPerformanceMetricsTable, "Python performance table renderer must be testable");

const adaptedRun = api.adaptSchemaV4Payload(payload).runs[0];
const payloadEndIndex = payload.performance.dates.indexOf(payload.data.asOf);
const diagnosticOptions = adaptedRun.factor_options.filter((row) => (
  row.selection_eligible === false
  && payload.performance.factorCurves[row.factor]
));
const diagnosticOptionWithReturn = diagnosticOptions.find((row) => (
  Number.isFinite(api.v4CurveReturn(
    payload.performance.factorCurves[row.factor],
    payloadEndIndex,
    252,
  ))
));
const diagnosticOption = diagnosticOptionWithReturn || diagnosticOptions[0];
assert(diagnosticOption, "fixture must expose a selection-excluded diagnostic factor curve");
const diagnosticStats = api.periodFactorStatsIncludingDiagnostic(
  adaptedRun,
  payload.data.asOf,
  "1Y",
  diagnosticOption.factor,
);
const diagnosticCurve = payload.performance.factorCurves[diagnosticOption.factor];
const expectedDiagnosticReturn = api.v4CurveReturn(diagnosticCurve, payloadEndIndex, 252);
assert.equal(diagnosticStats.rank, null, "a selection-excluded factor must not receive an eligible rank");
assert.equal(diagnosticStats.selection_eligible, false);
assert.equal(diagnosticStats.period_return, expectedDiagnosticReturn);
if (diagnosticOptionWithReturn) {
  assert(Number.isFinite(diagnosticStats.period_return), "an available diagnostic factor return must not disappear");
} else {
  assert.equal(diagnosticStats.period_return, null, "a missing diagnostic endpoint must remain unavailable");
}

const target = new FakeElement("div");
const selectedFactor = payload.selectedFactor;
const comparisonFactor = payload.performance.factorCurves.mom_12m ? "mom_12m" : selectedFactor;
const series = [
  { key: "selected", factor: selectedFactor, label: `선택 팩터 ${selectedFactor}` },
  { key: "best", factor: comparisonFactor, label: `선택 기간 최고 팩터 ${comparisonFactor}` },
  { key: "benchmark-SPY", symbol: "SPY", label: "SPY" },
  { key: "benchmark-^IXIC", symbol: "^IXIC", label: "나스닥 종합지수" },
  { key: "benchmark-QQQ", symbol: "QQQ", label: "QQQ" },
];
api.renderPythonPerformanceMetricsTable(target, series, [payload.performance.periods[0]]);

const tables = target.findAll("table");
assert.equal(tables.length, 1, "one requested period must render one period table");
const performanceRows = tables[0].findAll("tr");
const headerLabels = performanceRows[0].findAll("th").map((node) => node.textContent);
assert.equal(headerLabels.length, 5, "the period table must preserve four comparisons without IXIC");
assert.equal(headerLabels[0], "지표");
assert.match(headerLabels[1], new RegExp(`선택 팩터.*${selectedFactor}`));
assert.match(headerLabels[2], new RegExp(`선택 기간 최고.*${comparisonFactor}`));
assert.match(headerLabels[3], /SPY/);
assert.match(headerLabels[4], /QQQ/);
assert.equal(performanceRows.length, 9, "header plus eight exact Python metric rows must render");
const [performanceHeaderRow, ...performanceMetricRows] = performanceRows;
assert(
  performanceHeaderRow.findAll("th").every((cell) => cell.attributes.get("scope") === "col"),
  "every Python performance series heading must be a scoped column header",
);
for (const row of performanceMetricRows) {
  assert.equal(
    row.findAll("th").length + row.findAll("td").length,
    5,
    "each row must keep one metric plus four readable comparison columns",
  );
  assert.equal(row.findAll("th").length, 1, "each metric row needs exactly one row header");
  assert.equal(
    row.findAll("th")[0].attributes.get("scope"),
    "row",
    "each Python performance metric name must be a scoped row header",
  );
}
assert(!target.textContent.includes("^IXIC"), "IXIC must not leak into the period table text");
assert(!target.textContent.includes("나스닥 종합지수"), "the removed IXIC label must not leak into the period table note");
assert(!tables[0].attributes.get("aria-label").includes("나스닥"));
const performanceWrap = target.findAll("div").find((node) => node.className === "performance-table-wrap");
assert(performanceWrap, "the period table needs an internal scroll wrapper");
assert.equal(performanceWrap.attributes.get("role"), "region");
assert.equal(performanceWrap.attributes.get("tabindex"), "0");
assert.equal(performanceWrap.attributes.get("aria-describedby"), "python-performance-metrics-note");
assert.match(performanceWrap.attributes.get("aria-label"), /Python 성과 지표 표/);

const symbols = Array.from({ length: 27 }, (_, index) => `SYM${String(index + 1).padStart(2, "0")}`);
const sessions = Array.from({ length: 21 }, (_, sessionIndex) => ({
  date: `2026-06-${String(30 - sessionIndex).padStart(2, "0")}`,
  lastSignalDate: `2026-06-${String(29 - sessionIndex).padStart(2, "0")}`,
  lastExecutionDate: `2026-06-${String(30 - sessionIndex).padStart(2, "0")}`,
  executionStatus: "carried",
  cashWeight: 0,
  rows: symbols.slice(sessionIndex % 8, sessionIndex % 8 + 20).map((symbol, rank) => ({
    symbol,
    rank: rank + 1,
    actualWeight: 0.05,
    source: "실제 백테스트 보유 이력",
  })),
}));
const targetRows = symbols.slice(0, 20).map((symbol, rank) => ({
  symbol,
  rank: rank + 1,
  targetWeight: 0.05,
  factorScore: 20 - rank,
}));
const dailyHead = new FakeElement("thead");
const dailyBody = new FakeElement("tbody");
api.renderDailyWeightsTable(dailyHead, dailyBody, {
  sessions,
  targetRows,
  target: { status: "available", cashWeight: 0 },
  sourceKind: "selected_backtest_holding_history",
  factor: selectedFactor,
  canonicalFactor: selectedFactor,
});
const dailyHeaders = dailyHead.findAll("th").map((node) => node.textContent);
assert.equal(dailyHeaders.length, 2 + symbols.length * 2 + 2, "all 27 union symbols plus cash must render");
assert(
  dailyHead.findAll("th").every((cell) => cell.attributes.get("scope") === "col"),
  "every dynamically rebuilt daily-weight heading must remain a scoped column header",
);
assert(dailyHeaders.includes("SYM27 백테스트 보유"), "history symbols must not be truncated to 20/24");
assert(dailyHeaders.includes("SYM27 현재 연구 목표"), "each history symbol needs an honest target column");
assert(dailyHeaders.every((label) => !label.includes("저장") && !label.includes("시나리오")));
assert.equal(dailyBody.findAll("tr").length, 21, "one month of 21 holding sessions must render newest first");
assert.equal(dailyBody.findAll("tr")[0].findAll("td")[0].textContent, sessions[0].date);
assert.match(
  dailyBody.textContent,
  /0\.00%.*현재 목표 미편입/,
  "an available complete target must render an exact 0% for history-only symbols",
);

const noncanonicalBody = new FakeElement("tbody");
api.renderDailyWeightsTable(new FakeElement("thead"), noncanonicalBody, {
  sessions: sessions.slice(0, 1),
  targetRows: [],
  target: { status: "unavailable_noncanonical_factor", cashWeight: null, weights: [] },
  sourceKind: "factor_backtest_holding_history_sidecar",
  factor: "gap_resistant",
  canonicalFactor: selectedFactor,
});
const noncanonicalCells = noncanonicalBody.findAll("tr")[0].findAll("td");
assert.equal(
  noncanonicalCells.at(-1).textContent,
  "-",
  "noncanonical factor history must not clone the canonical current target cash weight",
);

const emptyBody = new FakeElement("tbody");
api.renderDailyWeightsTable(new FakeElement("thead"), emptyBody, {
  sessions: [],
  targetRows: [],
  target: {},
  sourceKind: "factor_history_unavailable",
  factor: "gap_resistant",
  canonicalFactor: selectedFactor,
});
assert.match(emptyBody.textContent, /실제 보유 이력이 없습니다/);
assert(!emptyBody.textContent.includes(selectedFactor), "missing factor data must not advertise a canonical fallback");

const currentOnlyHead = new FakeElement("thead");
const currentOnlyBody = new FakeElement("tbody");
api.renderDailyWeightsTable(currentOnlyHead, currentOnlyBody, {
  sessions: [],
  targetRows: [
    { symbol: "AAA", targetWeight: 0.6, factorScore: 2 },
    { symbol: "BBB", targetWeight: 0.4, factorScore: 1 },
  ],
  target: {
    factor: "gap_resistant",
    status: "available",
    signalDate: "2026-07-10",
    cashWeight: 0,
  },
  sourceKind: "factor_history_unavailable",
  factor: "gap_resistant",
  canonicalFactor: selectedFactor,
});
assert.equal(currentOnlyBody.findAll("tr").length, 1, "an exact current target must render without holding history");
assert.match(currentOnlyBody.textContent, /현재 목표 신호 2026-07-10/);
assert.match(currentOnlyBody.textContent, /60\.00%/);
assert.match(currentOnlyBody.textContent, /40\.00%/);
assert.match(currentOnlyBody.textContent, /0\.00%/);
assert.match(currentOnlyBody.textContent, /과거 보유 아님/);

const failClosedBody = new FakeElement("tbody");
api.renderDailyWeightsTable(new FakeElement("thead"), failClosedBody, {
  sessions: [],
  targetRows: [],
  target: {
    factor: "gap_resistant",
    status: "unavailable",
    signalDate: "2026-07-10",
    cashWeight: 1,
    reasons: ["insufficient_data"],
  },
  sourceKind: "factor_history_unavailable",
  factor: "gap_resistant",
  canonicalFactor: selectedFactor,
});
assert.match(failClosedBody.textContent, /100\.00%/);
assert.match(failClosedBody.textContent, /실패-폐쇄/);
assert.match(
  failClosedBody.findAll("td").at(-1).textContent,
  /^100\.00%.*실패-폐쇄 현금$/,
  "fail-closed cash must appear in the exact current-target cash cell",
);

const sidecarFailureStatus = new FakeElement("div");
api.appendFactorHoldingHistoryLoadStatus(sidecarFailureStatus, {
  __factorHoldingHistorySidecarError: "SHA-256이 manifest와 다릅니다.",
});
assert.match(sidecarFailureStatus.textContent, /팩터별 보유 이력/);
assert.match(sidecarFailureStatus.textContent, /검증 실패/);
assert.match(sidecarFailureStatus.textContent, /canonical 이외 팩터 이력은 표시하지 않음/);

const dateSelect = new FakeElement("select");
dateSelect.value = "2026-07-10";
const factorControlRun = {
  factor_leaders: [
    { date: "2026-07-10" },
    { date: "2026-07-09" },
  ],
  scenario_available_dates_by_factor: {
    previous_factor: ["2026-07-10"],
    clicked_factor: ["2026-07-09"],
  },
  factor_score_snapshots: [
    { factor: "previous_factor", rows: Array.from({ length: 20 }, () => ({})) },
    { factor: "clicked_factor", rows: Array.from({ length: 7 }, () => ({})) },
  ],
  latest_output_rows: [],
  summary: { data_as_of: "2026-07-10", selected_factor: "previous_factor" },
};
const controls = new Map([
  ["#date-select", dateSelect],
]);
context.document = {
  createElement: (tagName) => new FakeElement(tagName),
  querySelector: (selector) => controls.get(selector) || null,
  querySelectorAll: () => [],
};
api.syncFactorDependentControls(
  factorControlRun,
  "clicked_factor",
  "2026-07-10",
);
assert.deepEqual(
  dateSelect.children.map((option) => option.textContent),
  ["2026-07-10 · 팩터 수익률만", "2026-07-09 · 종목/비중 가능"],
  "joint-ranking factor selection must refresh date availability labels for the clicked factor",
);
assert.equal(dateSelect.value, "2026-07-10", "factor synchronization must preserve a valid preferred date");

console.log("PASS period DOM, 21-session holdings, and comparison-factor date controls");
