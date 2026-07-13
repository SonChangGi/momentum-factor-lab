import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

class FakeStyle {
  constructor() {
    this.values = new Map();
  }

  setProperty(name, value) {
    this.values.set(name, String(value));
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.className = "";
    this.style = new FakeStyle();
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
    this.children.push(...children);
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  addEventListener() {}

  findByClass(className) {
    const ownClasses = String(this.className).split(/\s+/).filter(Boolean);
    const matches = ownClasses.includes(className) ? [this] : [];
    return matches.concat(this.children.flatMap((child) => child.findByClass?.(className) || []));
  }
}

const source = readFileSync("momentum_factor_lab/web/dashboard.js", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");
const context = vm.createContext({ console, setTimeout, TextDecoder, TextEncoder, URL, URLSearchParams });
vm.runInContext(source, context, { filename: "momentum_factor_lab/web/dashboard.js" });
context.document = { createElement: (tagName) => new FakeElement(tagName) };

const api = context.__MFL_WEB_TESTS__;
assert(api?.CHART_PALETTE_CLASS_MAP, "the semantic chart palette map must be testable");
assert.equal(api.factorComparisonBarClass({ selected: true, best: true }), "chart-bar-focal");
assert.equal(api.factorComparisonBarClass({ best: true }), "chart-bar-best");
assert.equal(api.factorComparisonBarClass(), "chart-bar-context");
assert.equal(api.benchmarkPaletteClass("SPY"), "benchmark-spy");
assert.equal(api.benchmarkPaletteClass("^IXIC"), "benchmark-ixic");
assert.equal(api.benchmarkPaletteClass("QQQ"), "benchmark-qqq");
assert.equal(api.benchmarkPaletteClass("OTHER"), "benchmark");
assert.equal(api.canonicalPolicyClass("equal_weight"), "policy-equal-weight");
assert.equal(api.canonicalPolicyClass("capped_linear_rank"), "policy-capped-linear-rank");
assert.equal(api.canonicalPolicyClass("capped_vol_adjusted_rank"), "policy-capped-vol-adjusted-rank");
assert.equal(api.canonicalPolicyClass("score_liquidity_rank"), "policy-score-liquidity-rank");
assert.equal(api.canonicalSelectionStatusClass("eligible"), "status-eligible");
assert.equal(api.canonicalSelectionStatusClass("data_excluded"), "status-data-excluded");
assert.equal(api.canonicalSelectionStatusClass("extreme_event_excluded"), "status-extreme-event-excluded");

const focalBars = new FakeElement("div");
api.appendBarRow(focalBars, "선택 팩터", "+12.0%", 0.12, 0.2, { className: "chart-bar-focal" });
assert.match(focalBars.children[0].className, /chart-bar-focal/);
assert.equal(focalBars.findByClass("bar-fill")[0].style.values.get("--bar-width"), "60.0%");

const neutralBars = new FakeElement("div");
api.appendBarRow(neutralBars, "현금 / 미사용", "10.0%", 0.1, 0.2, { className: "chart-bar-neutral-open" });
assert.match(neutralBars.children[0].className, /chart-bar-neutral-open/);

const canonicalBars = new FakeElement("div");
api.appendCanonicalBar(canonicalBars, {
  label: "winsorized_12m",
  detail: "변동성 조정 순위 · 선정 적격",
  width: 87.5,
  valueLabel: "87.50",
  className: "policy-capped-vol-adjusted-rank status-eligible",
});
assert.match(canonicalBars.children[0].className, /policy-capped-vol-adjusted-rank/);
assert.match(canonicalBars.children[0].className, /status-eligible/);
assert.match(canonicalBars.children[0].textContent, /변동성 조정 순위 · 선정 적격/);
assert.equal(canonicalBars.findByClass("bar-fill")[0].style.width, "87.50%");

assert.match(css, /--chart-policy-equal:\s*var\(--chart-focal\)/);
assert.match(css, /--chart-policy-rank:\s*var\(--chart-teal\)/);
assert.match(css, /--chart-policy-vol:\s*var\(--chart-secondary\)/);
assert.match(css, /--chart-policy-liquidity:\s*var\(--chart-amber\)/);
assert.match(css, /\.canonical-bar-row\.status-data-excluded[\s\S]*background:\s*var\(--chart-open\)/);
assert.match(css, /\.line-path\.benchmark-spy\s*\{[^}]*var\(--chart-neutral-strong\)/);
assert.match(css, /\.line-path\.benchmark-ixic\s*\{[^}]*var\(--chart-neutral\)/);
assert.match(css, /\.line-path\.benchmark-qqq\s*\{[^}]*var\(--chart-secondary\)/);
assert.doesNotMatch(css, /\.line-path\.benchmark-(?:spy|ixic|qqq)\s*\{[^}]*(?:--danger|--warn)/i);

console.log("PASS semantic chart palette DOM classes, open states, and benchmark line styles");
