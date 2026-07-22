import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");
const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const context = vm.createContext({ console, setTimeout, TextDecoder, TextEncoder, URL, URLSearchParams });
vm.runInContext(source, context, { filename: "dashboard.js" });
const api = context.__MFL_WEB_TESTS__;

assert(api, "web test API must be exported without a DOM");
assert.equal(api.THEME_STORAGE_KEY, "quant-research-theme");
assert.deepEqual(
  Array.from(api.LEGACY_THEME_STORAGE_KEYS),
  ["momentum-factor-theme", "quant-dashboard-theme", "quant-calm-theme", "dram-price-theme"],
);

const expectedNavigation = [
  ">Hub<",
  ">Fear &amp; Greed<",
  ">Momentum<",
  ">DRAM<",
  ">Best Factor<",
  ">ETF<",
  ">SOX<",
  ">Risk Score<",
  ">Port<",
  ">Valuation<",
  ">Kelly<",
];
let previousIndex = -1;
for (const label of expectedNavigation) {
  const index = html.indexOf(label);
  assert(index > previousIndex, `${label} must follow the canonical project navigation order`);
  previousIndex = index;
}

for (const id of [
  "backtest-series-controls",
  "backtest-date-input",
  "backtest-date-reset",
  "backtest-value-card",
  "backtest-active-date",
  "backtest-active-series",
  "backtest-active-value",
  "backtest-chart",
]) {
  assert.match(html, new RegExp(`id="${id}"`));
}
assert.match(html, /id="backtest-chart"[\s\S]*tabindex="0"/);
assert.match(html, /id="analysis-settings" class="dashboard-disclosure/);
assert.doesNotMatch(html, /id="analysis-settings"[^>]*\bopen\b/);
assert.doesNotMatch(html, /자동 예약 실행(?:과 watchdog 예약)?은 현재 중지/);

assert.equal(api.nearestChartDate(["2026-07-17", "2026-07-20", "2026-07-21"], "2026-07-19"), "2026-07-20");
assert.equal(api.nearestChartDate(["2026-07-17", "2026-07-20"], null), "2026-07-20");
assert.deepEqual(
  api.chartPointAtDate([{ date: "2026-07-21", normalized: 1.25 }], "2026-07-21"),
  { date: "2026-07-21", normalized: 1.25 },
);
assert.equal(api.chartPointAtDate([{ date: "2026-07-21", normalized: 1.25 }], "2026-07-20"), null);
assert.equal(api.formatChartReturn(0.1234), "+12.34%");
assert.equal(api.formatChartReturn(-0.2), "-20.00%");
assert.equal(api.formatChartReturn(null), "관측 없음");

assert.match(source, /previewSeriesKey/);
assert.match(source, /previewDate/);
assert.match(source, /event\.key === 'ArrowLeft'/);
assert.match(source, /event\.key === 'ArrowRight'/);
assert.match(source, /event\.key === 'Home'/);
assert.match(source, /event\.key === 'End'/);
assert.doesNotMatch(source, /function renderWithBusy/);

assert.match(css, /\.chart-series-button/);
assert.match(css, /\.chart-date-guide/);
assert.match(css, /\.chart-active-point/);
assert.match(css, /min-height:\s*44px/);
assert.match(css, /font-size:\s*max\(\.75rem,\s*12px\)/);
assert.match(css, /@media \(max-width: 640px\)/);

console.log("PASS Quant Research common design v1 Momentum contract");
