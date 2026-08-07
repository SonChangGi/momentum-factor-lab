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
assert.match(html, /데이터 · 출처 · 운영 상세/);
assert.doesNotMatch(html, /계열과 날짜를 탐색해도 공식 결과와 분석 입력은 바뀌지 않습니다/);
assert.doesNotMatch(html, /비교 팩터만 바뀌며 Python 최고 팩터는 유지됩니다/);
assert.doesNotMatch(html, /<section class="disclaimer">/);
assert(
  html.indexOf('class="operations-note"') > html.indexOf('class="supporting-detail-stack"'),
  "the single research-use note belongs inside the closed operations detail",
);

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
assert.match(css, /Quant Research common design v1\.2/);
assert.match(css, /body\s*\{[\s\S]*?font-size:\s*15px;[\s\S]*?line-height:\s*1\.55;/);
assert.match(css, /\.site-nav\s*\{[\s\S]*?min-height:\s*58px;/);
assert.match(css, /\.site-nav-links a,[\s\S]*?font-size:\s*12px;[\s\S]*?font-weight:\s*650;/);
assert.match(css, /\.result-cards\s*\{[\s\S]*?grid-auto-flow:\s*column;[\s\S]*?overflow-x:\s*auto;/);
assert.match(css, /\.chart-series-controls\s*\{[\s\S]*?flex-wrap:\s*nowrap;[\s\S]*?overflow-x:\s*auto;/);

console.log("PASS Quant Research common design v1.2 Momentum contract");
