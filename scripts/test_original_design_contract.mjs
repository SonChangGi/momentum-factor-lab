import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");
const js = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const publishedHtml = readFileSync("docs/index.html", "utf8");
const assetVersion = createHash("sha256").update(css).update(js).digest("hex").slice(0, 12);
assert.equal(
  publishedHtml,
  html
    .replace("__TITLE__", "모멘텀 팩터 데일리 대시보드")
    .replaceAll("__ASSET_VERSION__", assetVersion),
  "published HTML must be the exact rendered template with the current asset version",
);

const baselineIds = [
  "run-status",
  "run-select",
  "date-select",
  "window-select",
  "factor-select",
  "research-input-form",
  "input-evaluation-years",
  "input-top-n",
  "input-max-weight",
  "input-transaction-cost",
  "input-slippage",
  "data-quality-summary",
  "tradability-gate-list",
  "selected-factor-method-steps",
  "factor-category-summary",
  "factor-rank-ic-summary",
  "factor-redundancy-summary",
  "factor-return-chart",
  "backtest-chart",
  "performance-metrics-table",
  "window-comparison-chart",
  "leader-trend-chart",
  "comparison-weight-chart",
  "comparison-weight-chart-meta",
  "weight-chart",
  "factor-table",
  "holdings-table",
  "daily-weights-table",
  "period-ranking-table",
  "manual-update-button",
  "copy-update-command",
  "page-bottom",
  "theme-toggle",
];
const additiveIds = [
  "canonical-research",
  "joint-policy-filter",
  "joint-factor-search",
  "joint-ranking-chart",
  "joint-ranking-table",
  "canonical-component-chart",
  "canonical-policy-cards",
  "canonical-guardrail-list",
  "canonical-data-contract",
  "canonical-universe-scope",
  "canonical-universe-evidence",
];

for (const id of [...baselineIds, ...additiveIds]) {
  assert.ok(html.includes(`id="${id}"`), `missing required 2026-07-10/additive element: ${id}`);
}

const htmlIds = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
assert.equal(new Set(htmlIds).size, htmlIds.length, "dashboard ids must remain unique");

const requiredProjectLinks = [
  "quant-dashboard/",
  "momentum-factor-lab/",
  "dram-price/",
  "best-factor/",
  "etf-tracking/",
  "sox/",
  "risk-score/",
  "port/",
  "valuation/",
];
for (const path of requiredProjectLinks) {
  assert.ok(html.includes(path), `missing original project navigation link: ${path}`);
}

assert.match(html, /결과 · 성과 기간 · 비교 팩터/);
assert.match(html, /Python 분석 조건/);
assert.match(html, /팩터 수익률 막대 차트/);
assert.match(html, /비교 팩터와 기간 수익률 1위/);
assert.match(html, /기간별 최고 팩터 비교/);
assert.match(html, /최근 30거래일 리더 추이/);
assert.match(html, /비교 팩터 선택 종목 비중/);
assert.match(html, /최고 팩터 선택 종목 비중/);
assert.match(html, /id="advanced-research-inputs" class="advanced-research-inputs"/);
assert.match(html, /class="core-research-inputs"/);
assert.match(html, /id="input-extreme-return"[^>]*step="0\.01"/);
assert.doesNotMatch(html, /그래프와 성과표는 현재 입력으로 Python이 계산한 원자료/);
assert.doesNotMatch(html, /현재 canonical 목표|브라우저 프록시 시나리오 입력|상위 10개 팩터 동일비중 합산/);
assert.match(html, /모든 팩터×정책 조합을 하나의 랭킹으로 비교/);
assert.match(html, /합성 점수 구성/);

const originalPrefix = css.split("\n").slice(0, 589).join("\n") + "\n";
assert.equal(
  createHash("sha256").update(originalPrefix).digest("hex"),
  "0e110db899b264ec4775f04fcd6a00b18d4618f857ada8a0c929a61ef6c29979",
  "the first 589 CSS lines must remain the reviewed Python-first design root",
);
assert.match(css, /\.bar-track,\s*\n\.bar-fill\s*\{\s*display:\s*block;/s);
assert.match(css, /--chart-focal:\s*var\(--accent\)/);
assert.match(css, /--chart-teal:\s*var\(--good\)/);
assert.match(css, /--chart-secondary:\s*var\(--violet\)/);
assert.match(css, /--chart-amber:\s*var\(--warn\)/);
assert.match(css, /--chart-neutral-strong:\s*var\(--muted-strong\)/);
assert.match(css, /--chart-policy-equal:\s*var\(--chart-focal\)/);
assert.match(css, /--chart-policy-rank:\s*var\(--chart-teal\)/);
assert.match(css, /--chart-policy-vol:\s*var\(--chart-secondary\)/);
assert.match(css, /--chart-policy-liquidity:\s*var\(--chart-amber\)/);
assert.match(css, /\.line-path\.benchmark-spy/);
assert.match(css, /\.line-path\.benchmark-ixic/);
assert.match(css, /\.line-path\.benchmark-qqq/);
assert.match(css, /\.line-path\.benchmark-spy\s*\{[^}]*var\(--chart-neutral-strong\)/);
assert.match(css, /\.line-path\.benchmark-ixic\s*\{[^}]*var\(--chart-neutral\)/);
assert.match(css, /\.line-path\.benchmark-qqq\s*\{[^}]*var\(--chart-secondary\)/);
assert.doesNotMatch(css, /\.line-path\.benchmark-(?:spy|ixic|qqq)\s*\{[^}]*(?:--danger|--warn)/i);
assert.match(css, /\.canonical-bar-row\.is-selected/);
assert.match(css, /\.canonical-bar-row\.status-data-excluded[\s\S]*background:\s*var\(--chart-open\)/);
assert.match(css, /\.canonical-bar-row\.chart-bar-focal \.bar-fill\s*\{\s*background:\s*var\(--chart-focal\)/);
assert.match(css, /\.component-chart \.canonical-bar-row\.chart-bar-component \.bar-fill\s*\{\s*background:\s*var\(--chart-focal\)/);
assert.match(css, /\.bar-row \.bar-fill\.negative,\s*\n\.trend-fill\.negative\s*\{[^}]*var\(--chart-negative\)/s);
assert.equal(
  [...css.matchAll(/var\(--chart-negative\)/g)].length,
  1,
  "the chart red token must be consumed only by the shared signed-negative rule",
);
assert.doesNotMatch(css, /#126f4d/i);
assert.doesNotMatch(css, /radial-gradient/i);

function cssBlock(marker) {
  const start = css.indexOf(marker);
  assert(start >= 0, `missing CSS block: ${marker}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

function hexToken(block, name) {
  const match = block.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert(match, `missing concrete color token --${name}`);
  return match[1];
}

function relativeLuminance(hex) {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((value) => (
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(left, right) {
  const leftLuminance = relativeLuminance(left);
  const rightLuminance = relativeLuminance(right);
  return (Math.max(leftLuminance, rightLuminance) + 0.05)
    / (Math.min(leftLuminance, rightLuminance) + 0.05);
}

for (const [theme, block] of [
  ["light", cssBlock(":root {")],
  ["dark", cssBlock('html[data-theme="dark"] {')],
]) {
  const background = hexToken(block, "panel");
  for (const token of ["accent", "accent-strong", "good", "warn", "danger", "violet", "muted", "muted-strong"]) {
    assert(
      contrastRatio(hexToken(block, token), background) >= 3,
      `${theme} --${token} must keep at least 3:1 graphical contrast against --panel`,
    );
  }
}

assert.match(js, /function adaptSchemaV4Payload/);
assert.match(js, /const CHART_PALETTE_CLASS_MAP = Object\.freeze/);
assert.match(js, /factorComparisonBarClass/);
assert.match(js, /benchmarkPaletteClass/);
assert.match(js, /canonicalSelectionStatusClass/);
assert.match(js, /comparison_benchmark_series/);
assert.match(js, /benchmark-spy/);
assert.match(js, /benchmark-ixic/);
assert.match(js, /benchmark-qqq/);
assert.match(js, /renderPythonPerformanceMetricsTable/);
assert.match(js, /portfolioHoldingsFromPayload/);
assert.match(js, /payload\.factorPortfolios\?\.\[factor\]/);
assert.doesNotMatch(js, /내부 평가불가 .*그래프 선 없음/);
assert.match(js, /state\.v4Payload\?\.performance\?\.periods/);
assert.match(js, /실제 백테스트 보유 이력/);
assert.match(js, /현재 연구 목표/);
assert.match(js, /dateTickMarks\(allDates\)/);
assert.match(js, /niceReturnTicks/);

console.log("PASS Python-first dynamic research UI inventory and schema-v4 design contract");
