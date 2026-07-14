import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync("momentum_factor_lab/web/index.html", "utf8");
const css = readFileSync("momentum_factor_lab/web/styles.css", "utf8");

assert.match(html, /모멘텀 팩터 데일리 대시보드/);
assert.match(html, /팩터 점수 50%·거래대금 30%·정보시점 기준 시가총액 20%/);
assert.match(html, /class="core-research-inputs"/);
assert.match(html, /<details id="advanced-research-inputs"/);
assert.match(html, /최대 일간 절대 수익률[\s\S]*max="10000"/);
assert.match(html, /<form id="research-input-form"[^>]*novalidate>/);
assert.match(html, /사용자 선택 팩터와 Python 최고 팩터/);
assert.match(html, /사용자 선택 팩터[\s\S]*선택 종목 비중/);
assert.match(html, /Python 최고 팩터[\s\S]*최고 팩터 선택 종목 비중/);
assert.doesNotMatch(html, /현재 canonical 목표|동일가중|기간 수익률 1위/);
assert.match(css, /\.core-research-inputs/);
assert.match(css, /\.advanced-research-input-grid/);
assert.match(css, /@media \(max-width: 720px\)/);

console.log("PASS input-first fixed-method design contract");
