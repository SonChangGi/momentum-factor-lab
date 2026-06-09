from __future__ import annotations

import html
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .portfolio import balanced_weights

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .workflow import RunResult


DASHBOARD_PERIODS: dict[str, int] = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}

PERIOD_LABELS: dict[str, str] = {
    "1M": "최근 1개월",
    "3M": "최근 3개월",
    "6M": "최근 6개월",
    "1Y": "최근 1년",
}

DEFAULT_SITE_TITLE = "모멘텀 팩터 데일리 대시보드"


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="assets/styles.css" />
</head>
<body>
  <header class="hero">
    <div>
      <p class="eyebrow">모멘텀 팩터 랩</p>
      <h1>{title}</h1>
      <p class="hero-copy">
        매일 미국 종가 기준으로 업데이트되는 모멘텀 팩터 비교 화면입니다.
        최근 기간별 최고 팩터와 일별 상위 종목, 모멘텀 신호, 표시용 투자 비중을 한 화면에서 비교합니다.
      </p>
    </div>
    <div class="status-card" id="run-status">데이터를 불러오는 중...</div>
  </header>

  <main>
    <section class="notice">
      <strong>중요:</strong> 이 웹사이트의 선택값은 브라우저에서 비교/표시만 바꾸며,
      다음 자동 실행 설정을 저장하지 않습니다. 매일 실행 input은 저장소의
      <code>.github/momentum-dashboard-config.json</code>에서 관리됩니다.
    </section>

    <section class="controls" aria-label="대시보드 입력값">
      <label>실행 결과
        <select id="run-select"></select>
      </label>
      <label>기준일
        <select id="date-select"></select>
      </label>
      <label>최근 기간
        <select id="window-select"></select>
      </label>
      <label>상위 N개 종목 수
        <input id="topn-input" type="number" min="1" max="50" value="20" />
      </label>
      <label>종목당 최대 비중
        <input id="max-weight-input" type="number" min="1" max="100" step="1" value="10" />
        <span class="unit">%</span>
      </label>
    </section>

    <section class="cards" aria-label="요약 카드">
      <article class="card">
        <span>선택된 최고 팩터</span>
        <strong id="best-factor">-</strong>
        <small id="best-factor-detail">-</small>
      </article>
      <article class="card">
        <span>기존 선택 팩터</span>
        <strong id="selected-factor">-</strong>
        <small id="selected-factor-detail">-</small>
      </article>
      <article class="card">
        <span>추천/신호 상태</span>
        <strong id="recommendation-status">-</strong>
        <small id="data-provider">-</small>
      </article>
      <article class="card">
        <span>표시용 총 비중</span>
        <strong id="weight-summary">-</strong>
        <small>잔여 비중은 현금/미투자 영역으로 표시합니다.</small>
      </article>
    </section>

    <section class="panel visual-panel" id="visual-dashboard">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">시각화 대시보드</p>
          <h2>팩터별 비교 · 기간별 리더 · 상위 N개 비중</h2>
        </div>
        <p>
          위 입력값을 바꾸면 아래 차트가 즉시 갱신됩니다. 표보다 먼저 팩터별 상대 강도와
          상위 종목 비중을 빠르게 파악하도록 구성했습니다.
        </p>
      </div>
      <div class="viz-grid">
        <article class="viz-card wide">
          <div class="viz-card-heading">
            <div>
        <p class="eyebrow">팩터 수익률</p>
              <h3>팩터 수익률 막대 차트</h3>
            </div>
            <span id="factor-chart-meta" class="chart-meta">-</span>
          </div>
          <div id="factor-return-chart" class="bar-chart" aria-live="polite"></div>
        </article>
        <article class="viz-card">
          <div class="viz-card-heading">
            <div>
              <p class="eyebrow">기간 비교</p>
              <h3>기간별 최고 팩터 비교</h3>
            </div>
          </div>
          <div id="window-comparison-chart" class="window-chart" aria-live="polite"></div>
        </article>
        <article class="viz-card">
          <div class="viz-card-heading">
            <div>
              <p class="eyebrow">리더 추이</p>
              <h3>최근 30거래일 리더 추이</h3>
            </div>
          </div>
          <div id="leader-trend-chart" class="trend-chart" aria-live="polite"></div>
        </article>
        <article class="viz-card">
          <div class="viz-card-heading">
            <div>
              <p class="eyebrow">투자 비중</p>
              <h3>상위 N개 투자 비중 시각화</h3>
            </div>
            <span id="weight-chart-meta" class="chart-meta">-</span>
          </div>
          <div id="weight-chart" class="bar-chart compact-bars" aria-live="polite"></div>
        </article>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">기간별 팩터 비교</p>
          <h2>최근 기간별 최고 모멘텀 팩터</h2>
        </div>
        <p>각 기준일마다 선택한 최근 기간의 누적 수익률이 가장 높았던 팩터를 표시합니다.</p>
      </div>
      <div class="table-wrap">
        <table id="factor-table">
          <thead>
            <tr>
              <th>기준일</th>
              <th>기간</th>
              <th>최고 팩터</th>
              <th>기간 수익률</th>
              <th>기존 선택 팩터 수익률</th>
              <th>기존 선택 팩터 순위</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">상위 N개 종목 비교</p>
          <h2>일별 상위 종목 · 모멘텀 신호 · 표시용 투자 비중</h2>
        </div>
        <p>비중은 선택한 상위 N개 종목 수와 종목당 최대 비중으로 브라우저에서 동일가중 상한 방식으로 다시 계산합니다.</p>
      </div>
      <div class="table-wrap">
        <table id="holdings-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>종목</th>
              <th>모멘텀 신호</th>
              <th>표시용 비중</th>
              <th>팩터</th>
              <th>신호일</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="panel two-col">
      <div>
        <p class="eyebrow">최신 팩터 랭킹</p>
        <h2>기준일별 기간 수익률 상위 팩터</h2>
        <div class="table-wrap compact">
          <table id="period-ranking-table">
            <thead><tr><th>기간</th><th>팩터</th><th>수익률</th><th>순위</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
      <div class="explain">
        <p class="eyebrow">읽는 방법</p>
        <h2>대시보드 설명</h2>
        <ul>
          <li><strong>최고 팩터</strong>는 선택 기간의 누적 전략 수익률이 가장 높은 팩터입니다.</li>
          <li><strong>모멘텀 신호</strong>는 해당 팩터가 계산한 종목별 점수이며, 높을수록 상위 후보입니다.</li>
          <li><strong>표시용 비중</strong>은 투자 조언이 아니라 비교를 돕기 위한 모델 비중입니다.</li>
          <li>데이터 품질, 유동성, 생존편향, 무료 데이터 한계는 기존 리포트와 동일하게 적용됩니다.</li>
        </ul>
      </div>
    </section>

    <section class="disclaimer">
      <h2>주의 및 한계</h2>
      <p>
        본 대시보드는 연구/의사결정 보조용이며 개인화된 투자, 세무, 법률 또는 매매 조언이 아닙니다.
        무료/공개 데이터의 누락, 조정가격 차이, 생존편향, 유동성/용량 한계가 있을 수 있습니다.
      </p>
    </section>
  </main>

  <footer>
    <span>모멘텀 팩터 랩에서 생성</span>
    <span id="generated-at"></span>
  </footer>
  <script src="assets/dashboard.js"></script>
</body>
</html>
"""


CSS_CONTENT = """:root {
  color-scheme: light;
  --bg: #f6f7fb;
  --panel: #ffffff;
  --ink: #132033;
  --muted: #64748b;
  --line: #dbe3ef;
  --accent: #2457d6;
  --accent-soft: #e8efff;
  --good: #087f5b;
  --warn: #b7791f;
  font-family: Inter, Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); }
.hero {
  display: flex; justify-content: space-between; gap: 2rem; align-items: stretch;
  padding: 3rem clamp(1rem, 4vw, 4rem); color: white;
  background: linear-gradient(135deg, #132033 0%, #2457d6 72%, #44b3ff 100%);
}
.hero h1 { margin: .25rem 0 1rem; font-size: clamp(2rem, 5vw, 4rem); }
.hero-copy { max-width: 760px; line-height: 1.7; opacity: .92; }
.eyebrow { margin: 0 0 .35rem; color: var(--accent); font-weight: 800; letter-spacing: .08em; text-transform: uppercase; font-size: .78rem; }
.hero .eyebrow { color: #c7dcff; }
.status-card { min-width: 260px; align-self: center; border: 1px solid rgba(255,255,255,.32); border-radius: 24px; padding: 1.25rem; background: rgba(255,255,255,.14); backdrop-filter: blur(8px); line-height: 1.6; }
main { padding: 1.5rem clamp(1rem, 4vw, 4rem) 3rem; }
.notice, .panel, .disclaimer, .controls, .card { background: var(--panel); border: 1px solid var(--line); box-shadow: 0 12px 30px rgba(15, 23, 42, .06); }
.notice { padding: 1rem 1.25rem; border-radius: 18px; margin-bottom: 1.25rem; color: #334155; }
.controls { display: grid; grid-template-columns: repeat(5, minmax(160px, 1fr)); gap: 1rem; padding: 1rem; border-radius: 22px; margin-bottom: 1.25rem; }
label { font-size: .86rem; color: var(--muted); font-weight: 700; display: flex; flex-direction: column; gap: .45rem; position: relative; }
select, input { width: 100%; border: 1px solid var(--line); border-radius: 12px; padding: .72rem .8rem; color: var(--ink); background: #fff; font: inherit; }
.unit { position: absolute; right: .8rem; bottom: .75rem; color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 1rem; margin-bottom: 1.25rem; }
.card { border-radius: 22px; padding: 1.1rem; }
.card span { color: var(--muted); font-weight: 700; font-size: .85rem; }
.card strong { display: block; margin: .45rem 0; font-size: 1.35rem; }
.card small { color: var(--muted); line-height: 1.5; }
.panel { border-radius: 26px; padding: 1.25rem; margin-bottom: 1.25rem; }
.panel-heading { display: flex; justify-content: space-between; gap: 1.5rem; align-items: end; margin-bottom: 1rem; }
.panel-heading h2, .explain h2, .disclaimer h2 { margin: 0; }
.panel-heading p { margin: 0; color: var(--muted); max-width: 620px; line-height: 1.6; }
.table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 18px; }
table { width: 100%; border-collapse: collapse; min-width: 760px; background: #fff; }
th, td { text-align: left; padding: .78rem .9rem; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { background: #f8fafc; color: #475569; font-size: .8rem; }
td { font-size: .92rem; }
tbody tr:hover { background: #f8fbff; }
.two-col { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 1.5rem; }
.compact table { min-width: 420px; }
.explain { background: var(--accent-soft); border-radius: 22px; padding: 1.25rem; }
.explain ul { padding-left: 1.2rem; line-height: 1.75; color: #334155; }
.disclaimer { border-radius: 22px; padding: 1.25rem; color: #475569; line-height: 1.7; }
.positive { color: var(--good); font-weight: 800; }
.negative { color: #c92a2a; font-weight: 800; }
.badge { display: inline-flex; padding: .2rem .55rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 800; }
.visual-panel { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
.viz-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.viz-card {
  border: 1px solid var(--line); border-radius: 22px; padding: 1rem;
  background: rgba(255,255,255,.86); box-shadow: 0 10px 24px rgba(15, 23, 42, .05);
}
.viz-card.wide { grid-column: 1 / -1; }
.viz-card-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; margin-bottom: .9rem; }
.viz-card h3 { margin: 0; font-size: 1.05rem; }
.chart-meta { color: var(--muted); font-size: .82rem; font-weight: 800; white-space: nowrap; }
.bar-chart { display: grid; gap: .62rem; }
.bar-row { display: grid; grid-template-columns: minmax(120px, .9fr) minmax(180px, 2fr) 88px; gap: .75rem; align-items: center; }
.bar-label { font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { height: 12px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.bar-fill { height: 100%; width: var(--bar-width, 0%); border-radius: inherit; background: linear-gradient(90deg, var(--accent), #44b3ff); }
.bar-fill.negative { background: linear-gradient(90deg, #f03e3e, #ff8787); }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; font-weight: 800; }
.compact-bars .bar-row { grid-template-columns: minmax(72px, .55fr) minmax(140px, 1.6fr) 76px; }
.window-chart { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.window-chip { border: 1px solid var(--line); border-radius: 18px; padding: .85rem; background: #fff; }
.window-chip span { display: block; color: var(--muted); font-size: .78rem; font-weight: 800; }
.window-chip strong { display: block; margin: .35rem 0; font-size: 1.05rem; }
.window-chip small { color: var(--muted); line-height: 1.45; }
.trend-chart { min-height: 220px; }
.trend-bars { display: flex; gap: .35rem; align-items: end; height: 180px; padding: .75rem .35rem .25rem; border: 1px solid var(--line); border-radius: 18px; background: #fff; overflow-x: auto; }
.trend-bar { display: flex; flex-direction: column; align-items: center; justify-content: end; min-width: 28px; height: 100%; gap: .35rem; }
.trend-fill { width: 18px; height: var(--bar-height, 0%); min-height: 3px; border-radius: 999px 999px 4px 4px; background: linear-gradient(180deg, #44b3ff, var(--accent)); }
.trend-fill.negative { background: linear-gradient(180deg, #ff8787, #f03e3e); }
.trend-label { color: var(--muted); font-size: .68rem; writing-mode: vertical-rl; max-height: 46px; overflow: hidden; }
.empty-state { color: var(--muted); border: 1px dashed var(--line); border-radius: 18px; padding: 1rem; background: #fff; line-height: 1.6; }
footer { display: flex; justify-content: space-between; gap: 1rem; color: var(--muted); padding: 1.5rem clamp(1rem, 4vw, 4rem); }
@media (max-width: 980px) {
  .hero, .panel-heading, footer { flex-direction: column; }
  .controls, .cards, .two-col, .viz-grid, .window-chart { grid-template-columns: 1fr; }
  .bar-row, .compact-bars .bar-row { grid-template-columns: 1fr; gap: .35rem; }
  .bar-value { text-align: left; }
  .status-card { width: 100%; }
}
"""


JS_CONTENT = """const state = {
  data: null,
  activeRunIndex: 0,
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 4 });
};

const classForNumber = (value) => Number(value) >= 0 ? 'positive' : 'negative';
const textValue = (value) => value === null || value === undefined ? '-' : String(value);

function currentRun() {
  const runs = state.data?.runs || [];
  return runs[state.activeRunIndex] || runs[state.data?.latest_run_index || 0] || state.data?.latest || {};
}

function uniqueDates(run) {
  const source = (run.factor_leaders || []).length ? run.factor_leaders : (run.holdings || []);
  return [...new Set(source.map((row) => row.date).filter(Boolean))].sort().reverse();
}

function selectedDate() {
  return document.querySelector('#date-select').value;
}

function selectedWindow() {
  return document.querySelector('#window-select').value;
}

function recomputeWeights(rows, topN, maxWeight) {
  const selected = rows.slice(0, topN);
  if (!selected.length) return [];
  const base = Math.min(1 / selected.length, maxWeight);
  return selected.map((row, index) => ({ ...row, display_weight: base, display_rank: index + 1 }));
}

function setText(selector, value) {
  document.querySelector(selector).textContent = textValue(value);
}

function appendCell(tr, value, options = {}) {
  const td = document.createElement('td');
  if (options.className) td.className = options.className;
  if (options.badge) {
    const span = document.createElement('span');
    span.className = 'badge';
    span.textContent = textValue(value);
    td.appendChild(span);
  } else if (options.strong) {
    const strong = document.createElement('strong');
    strong.textContent = textValue(value);
    td.appendChild(strong);
  } else {
    td.textContent = textValue(value);
  }
  tr.appendChild(td);
}

function appendEmpty(selector, message) {
  const target = document.querySelector(selector);
  target.replaceChildren();
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.textContent = message;
  target.appendChild(empty);
}

function barWidth(value, maxAbs) {
  if (!Number.isFinite(Number(value)) || maxAbs <= 0) return '0%';
  return `${Math.max(3, Math.min(100, Math.abs(Number(value)) / maxAbs * 100)).toFixed(1)}%`;
}

function currentWeightedHoldings() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const maxWeight = Math.max(0.01, Math.min(1, Number(document.querySelector('#max-weight-input').value || 10) / 100));
  const rows = (run.holdings || []).filter((row) => row.date === date && row.window === windowKey);
  const weighted = recomputeWeights(rows, topN, maxWeight);
  const total = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  return { weighted, total, topN, maxWeight };
}

function appendBarRow(target, label, valueLabel, value, maxAbs) {
  const row = document.createElement('div');
  row.className = 'bar-row';

  const labelNode = document.createElement('div');
  labelNode.className = 'bar-label';
  labelNode.textContent = textValue(label);

  const track = document.createElement('div');
  track.className = 'bar-track';
  const fill = document.createElement('div');
  fill.className = `bar-fill ${Number(value) < 0 ? 'negative' : ''}`;
  fill.style.setProperty('--bar-width', barWidth(value, maxAbs));
  track.appendChild(fill);

  const valueNode = document.createElement('div');
  valueNode.className = `bar-value ${classForNumber(value)}`;
  valueNode.textContent = valueLabel;

  row.append(labelNode, track, valueNode);
  target.appendChild(row);
}

function fillControls() {
  const runSelect = document.querySelector('#run-select');
  runSelect.replaceChildren();
  (state.data.runs || []).forEach((run, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${run.summary?.data_as_of || 'unknown'} · ${run.summary?.selected_factor || '-'}`;
    runSelect.appendChild(option);
  });
  runSelect.value = String(state.activeRunIndex);

  const run = currentRun();
  const windows = run.periods || [];
  const windowSelect = document.querySelector('#window-select');
  windowSelect.replaceChildren();
  windows.forEach((period) => {
    const option = document.createElement('option');
    option.value = period.key;
    option.textContent = period.label;
    windowSelect.appendChild(option);
  });
  windowSelect.value = windows[1]?.key || windows[0]?.key || '1M';

  const dates = uniqueDates(run);
  const dateSelect = document.querySelector('#date-select');
  dateSelect.replaceChildren();
  dates.forEach((date) => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = date;
    dateSelect.appendChild(option);
  });
  if (dates.length) dateSelect.value = dates[0];

  document.querySelector('#topn-input').value = run.summary?.default_top_n || 20;
  document.querySelector('#max-weight-input').value = Math.round((run.summary?.default_max_weight || 0.1) * 100);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const row = (run.factor_leaders || []).find((item) => item.date === date && item.window === windowKey);
  const summary = run.summary || {};
  setText('#best-factor', row?.best_factor || '-');
  setText('#best-factor-detail', row ? `${row.window_label} 수익률 ${formatPercent(row.best_return)}` : '-');
  setText('#selected-factor', summary.selected_factor || '-');
  setText('#selected-factor-detail', row ? `선택 팩터 순위 ${row.selected_factor_rank || '-'} · ${formatPercent(row.selected_factor_return)}` : '-');
  setText('#recommendation-status', summary.recommendation_status || '-');
  setText('#data-provider', `${summary.data_as_of || '-'} · ${summary.provider || '-'}`);

  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  const strong = document.createElement('strong');
  strong.textContent = summary.data_as_of || '-';
  statusCard.append(strong, document.createElement('br'), textValue(summary.provider || '-'), document.createElement('br'), textValue(summary.recommendation_output_label || ''));

  setText('#generated-at', `대시보드 생성: ${state.data.generated_at_utc || '-'}`);
}

function renderFactorTable() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, row.best_factor);
    appendCell(tr, formatPercent(row.best_return), { className: classForNumber(row.best_return) });
    appendCell(tr, formatPercent(row.selected_factor_return), { className: classForNumber(row.selected_factor_return) });
    appendCell(tr, row.selected_factor_rank || '-');
    tbody.appendChild(tr);
  });
}

function renderHoldingsTable() {
  const { weighted, total } = currentWeightedHoldings();
  setText('#weight-summary', `${formatPercent(total)} / 현금 ${formatPercent(Math.max(0, 1 - total))}`);
  const tbody = document.querySelector('#holdings-table tbody');
  tbody.replaceChildren();
  weighted.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.display_rank);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.display_weight));
    appendCell(tr, row.factor);
    appendCell(tr, row.score_date || row.date);
    tbody.appendChild(tr);
  });
}

function renderFactorReturnChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const rows = (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .slice(0, 10);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText('#factor-chart-meta', `${date || '-'} · ${windowLabel}`);
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(target, `${row.rank}. ${row.factor}`, formatPercent(row.period_return), row.period_return, maxAbs));
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const periodOrder = (run.periods || []).map((period) => period.key);
  const rows = (run.factor_leaders || [])
    .filter((row) => row.date === date)
    .sort((a, b) => periodOrder.indexOf(a.window) - periodOrder.indexOf(b.window));
  const target = document.querySelector('#window-comparison-chart');
  target.replaceChildren();
  if (!rows.length) {
    appendEmpty('#window-comparison-chart', '선택한 기준일에 기간별 최고 팩터 데이터가 없습니다.');
    return;
  }
  rows.forEach((row) => {
    const chip = document.createElement('div');
    chip.className = 'window-chip';
    const label = document.createElement('span');
    label.textContent = row.window_label || row.window;
    const factor = document.createElement('strong');
    factor.textContent = row.best_factor || '-';
    const detail = document.createElement('small');
    detail.textContent = `최고 수익률 ${formatPercent(row.best_return)} · 기존 선택 팩터 순위 ${row.selected_factor_rank || '-'}`;
    chip.append(label, factor, detail);
    target.appendChild(chip);
  });
}

function renderLeaderTrendChart() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const rows = (run.factor_leaders || [])
    .filter((row) => row.window === windowKey)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .slice(-30);
  const target = document.querySelector('#leader-trend-chart');
  target.replaceChildren();
  if (!rows.length) {
    appendEmpty('#leader-trend-chart', '선택한 기간에 최근 리더 추이 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.best_return) || 0)), 0.01);
  const bars = document.createElement('div');
  bars.className = 'trend-bars';
  rows.forEach((row) => {
    const bar = document.createElement('div');
    bar.className = 'trend-bar';
    bar.title = `${row.date} · ${row.best_factor} · ${formatPercent(row.best_return)}`;
    const fill = document.createElement('div');
    fill.className = `trend-fill ${Number(row.best_return) < 0 ? 'negative' : ''}`;
    fill.style.setProperty('--bar-height', barWidth(row.best_return, maxAbs));
    const label = document.createElement('div');
    label.className = 'trend-label';
    label.textContent = String(row.date || '').slice(5);
    bar.append(fill, label);
    bars.appendChild(bar);
  });
  target.appendChild(bars);
}

function renderWeightChart() {
  const { weighted, total, topN, maxWeight } = currentWeightedHoldings();
  const target = document.querySelector('#weight-chart');
  target.replaceChildren();
  setText('#weight-chart-meta', `상위 ${topN}개 · 최대 ${formatPercent(maxWeight)}`);
  if (!weighted.length) {
    appendEmpty('#weight-chart', '선택한 기준일과 기간에 표시할 상위 종목 데이터가 없습니다.');
    return;
  }
  const maxWeightValue = Math.max(...weighted.map((row) => Number(row.display_weight) || 0), 0.01);
  weighted.slice(0, 15).forEach((row) => appendBarRow(target, row.symbol, formatPercent(row.display_weight), row.display_weight, maxWeightValue));
  const cash = Math.max(0, 1 - total);
  if (cash > 0) {
    appendBarRow(target, '현금/미투자', formatPercent(cash), cash, Math.max(maxWeightValue, cash));
  }
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const rows = (run.factor_period_rankings || []).filter((row) => row.date === date).slice(0, 40);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.window_label);
    appendCell(tr, row.factor);
    appendCell(tr, formatPercent(row.period_return), { className: classForNumber(row.period_return) });
    appendCell(tr, row.rank);
    tbody.appendChild(tr);
  });
}

function renderAll() {
  renderSummary();
  renderFactorReturnChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
  renderFactorTable();
  renderHoldingsTable();
  renderPeriodRankingTable();
}

fetch('data/dashboard.json')
  .then((response) => response.json())
  .then((payload) => {
    if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.runs)) {
      throw new Error('지원하지 않는 대시보드 데이터 형식입니다.');
    }
    state.data = payload;
    state.activeRunIndex = Number.isInteger(payload.latest_run_index) ? payload.latest_run_index : Math.max(0, payload.runs.length - 1);
    fillControls();
    renderAll();
    document.querySelector('#run-select').addEventListener('change', (event) => {
      state.activeRunIndex = Number(event.target.value || 0);
      fillControls();
      renderAll();
    });
    ['#date-select', '#window-select', '#topn-input', '#max-weight-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', renderAll);
      document.querySelector(selector).addEventListener('change', renderAll);
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
"""


def build_dashboard_payload(
    result: RunResult,
    *,
    max_history_days: int = 90,
    max_holdings_per_period: int = 25,
    top_factor_count: int = 5,
) -> dict[str, Any]:
    """Build the compact JSON object consumed by the static dashboard."""

    periods = [
        {"key": key, "label": PERIOD_LABELS[key], "trading_days": days}
        for key, days in DASHBOARD_PERIODS.items()
    ]
    summary = _dashboard_summary(result)
    factor_returns = _factor_period_returns(result)
    leader_rows = _factor_leader_rows(
        factor_returns,
        selected_factor=result.selected_factor,
        max_history_days=max_history_days,
    )
    ranking_rows = _factor_period_ranking_rows(
        factor_returns,
        max_history_days=max_history_days,
        top_factor_count=top_factor_count,
    )
    holding_rows = _holding_rows(
        result,
        leader_rows,
        max_holdings_per_period=max_holdings_per_period,
    )
    latest_recommendations = result.recommendations.head(result.config.top_n).to_dict(orient="records")
    return _json_safe(
        {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "summary": summary,
            "periods": periods,
            "factor_leaders": leader_rows,
            "factor_period_rankings": ranking_rows,
            "holdings": holding_rows,
            "latest_output_rows": latest_recommendations,
            "notes_ko": [
                "웹사이트 입력값은 브라우저 표시용이며 다음 자동 실행 설정을 저장하지 않습니다.",
                "자동 실행 input은 .github/momentum-dashboard-config.json에서 관리합니다.",
                "모든 결과는 연구/의사결정 보조용이며 투자 조언이 아닙니다.",
            ],
        }
    )


def write_dashboard_site(
    run_result_patterns: str | Path | Iterable[str | Path],
    site_dir: str | Path,
    *,
    title: str = DEFAULT_SITE_TITLE,
) -> dict[str, str]:
    """Write a static Korean dashboard site for one or more run-result JSON files."""

    paths = _expand_run_result_paths(run_result_patterns)
    payloads = [_payload_from_run_json(path) for path in paths]
    payloads.sort(key=lambda payload: str(payload.get("summary", {}).get("run_timestamp_utc", "")))
    combined = _json_safe(
        {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "title": title,
            "runs": payloads,
            "latest_run_index": len(payloads) - 1,
        }
    )
    if not payloads:
        raise ValueError("at least one run-results JSON file is required")

    site_path = Path(site_dir)
    data_dir = site_path / "data"
    assets_dir = site_path / "assets"
    data_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    index_path = site_path / "index.html"
    css_path = assets_dir / "styles.css"
    js_path = assets_dir / "dashboard.js"
    data_path = data_dir / "dashboard.json"

    escaped_title = html.escape(title, quote=True)
    index_path.write_text(HTML_TEMPLATE.format(title=escaped_title), encoding="utf-8")
    css_path.write_text(CSS_CONTENT, encoding="utf-8")
    js_path.write_text(JS_CONTENT, encoding="utf-8")
    data_path.write_text(
        json.dumps(combined, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )

    return {
        "index": str(index_path),
        "css": str(css_path),
        "js": str(js_path),
        "data": str(data_path),
    }


def _dashboard_summary(result: RunResult) -> dict[str, Any]:
    return {
        "run_timestamp_utc": result.metadata.get("run_timestamp_utc"),
        "data_as_of": result.metadata.get("data_as_of"),
        "provider": result.metadata.get("provider"),
        "selected_factor": result.selected_factor,
        "selected_reason": result.selected_reason,
        "recommendation_status": result.metadata.get("recommendation_status"),
        "recommendation_output_label": result.metadata.get("recommendation_output_label"),
        "fresh_live_data_available": result.metadata.get("fresh_live_data_available"),
        "decision_support_tier": result.metadata.get("decision_support_tier"),
        "execution_limitations": result.metadata.get("execution_limitations", []),
        "tradability_blockers": result.metadata.get("tradability_blockers", []),
        "default_top_n": result.config.top_n,
        "default_max_weight": result.config.max_weight,
        "benchmark": result.config.benchmark,
        "universe_profile": result.config.universe_profile,
        "factor_selection_mode": result.metadata.get("factor_selection_mode"),
        "candidate_universe_size": result.metadata.get("candidate_universe_size"),
        "eligible_price_universe_size": result.metadata.get("eligible_price_universe_size"),
        "factor_count": result.metadata.get("factor_count"),
    }


def _factor_period_returns(result: RunResult) -> dict[str, pd.DataFrame]:
    returns_by_factor = {
        name: backtest.returns.dropna().sort_index()
        for name, backtest in result.backtests.items()
        if not backtest.returns.empty
    }
    if not returns_by_factor:
        return {key: pd.DataFrame() for key in DASHBOARD_PERIODS}
    returns = pd.DataFrame(returns_by_factor).sort_index()
    period_returns: dict[str, pd.DataFrame] = {}
    for key, days in DASHBOARD_PERIODS.items():
        period_returns[key] = (1.0 + returns).rolling(days, min_periods=days).apply(
            np.prod,
            raw=True,
        ) - 1.0
    return period_returns


def _factor_leader_rows(
    period_returns: dict[str, pd.DataFrame],
    *,
    selected_factor: str,
    max_history_days: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window_key, frame in period_returns.items():
        if frame.empty:
            continue
        frame = frame.dropna(how="all").tail(max_history_days)
        for date, values in frame.iterrows():
            clean = values.dropna().sort_values(ascending=False)
            if clean.empty:
                continue
            selected_return = values.get(selected_factor, np.nan)
            selected_rank = None
            if selected_factor in clean.index:
                selected_rank = int(clean.index.get_loc(selected_factor) + 1)
            rows.append(
                {
                    "date": _date_str(date),
                    "window": window_key,
                    "window_label": PERIOD_LABELS[window_key],
                    "best_factor": str(clean.index[0]),
                    "best_return": float(clean.iloc[0]),
                    "selected_factor": selected_factor,
                    "selected_factor_return": _float_or_none(selected_return),
                    "selected_factor_rank": selected_rank,
                    "factor_count": int(clean.size),
                }
            )
    return rows


def _factor_period_ranking_rows(
    period_returns: dict[str, pd.DataFrame],
    *,
    max_history_days: int,
    top_factor_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window_key, frame in period_returns.items():
        if frame.empty:
            continue
        for date, values in frame.dropna(how="all").tail(max_history_days).iterrows():
            clean = values.dropna().sort_values(ascending=False).head(top_factor_count)
            for rank, (factor, value) in enumerate(clean.items(), start=1):
                rows.append(
                    {
                        "date": _date_str(date),
                        "window": window_key,
                        "window_label": PERIOD_LABELS[window_key],
                        "rank": rank,
                        "factor": str(factor),
                        "period_return": float(value),
                    }
                )
    return rows


def _holding_rows(
    result: RunResult,
    leader_rows: list[dict[str, Any]],
    *,
    max_holdings_per_period: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    score_indexes = {
        factor: pd.DatetimeIndex(scores.index)
        for factor, scores in result.factor_scores.items()
        if not scores.empty
    }
    for leader in leader_rows:
        factor = leader["best_factor"]
        scores = result.factor_scores.get(factor)
        score_index = score_indexes.get(factor)
        if scores is None or scores.empty or score_index is None or score_index.empty:
            continue
        requested_date = pd.Timestamp(leader["date"])
        score_date = _nearest_score_date(score_index, requested_date)
        if score_date is None:
            continue
        row_scores = scores.loc[score_date].dropna().sort_values(ascending=False)
        if row_scores.empty:
            continue
        weights = balanced_weights(
            row_scores,
            top_n=min(max_holdings_per_period, result.config.top_n),
            max_weight=result.config.max_weight,
        )
        for rank, (symbol, score) in enumerate(row_scores.head(max_holdings_per_period).items(), start=1):
            rows.append(
                {
                    "date": leader["date"],
                    "window": leader["window"],
                    "window_label": leader["window_label"],
                    "factor": factor,
                    "score_date": _date_str(score_date),
                    "rank": rank,
                    "symbol": str(symbol),
                    "score": float(score),
                    "default_weight": _float_or_none(weights.get(symbol, 0.0)),
                }
            )
    return rows


def _nearest_score_date(index: pd.DatetimeIndex, requested_date: pd.Timestamp) -> pd.Timestamp | None:
    positions = index.searchsorted(requested_date, side="right") - 1
    if positions < 0:
        return None
    return pd.Timestamp(index[int(positions)])


def _payload_from_run_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("dashboard"), dict):
        dashboard = payload["dashboard"]
        dashboard.setdefault("source_json", str(path))
        return dashboard
    return _fallback_dashboard_payload(payload, path)


def _fallback_dashboard_payload(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    config = payload.get("config", {}) if isinstance(payload.get("config"), dict) else {}
    output_key = metadata.get("recommendation_output_key", "recommendations")
    rows = payload.get(output_key, []) if isinstance(payload.get(output_key), list) else []
    summary = {
        "run_timestamp_utc": metadata.get("run_timestamp_utc"),
        "data_as_of": metadata.get("data_as_of"),
        "provider": metadata.get("provider"),
        "selected_factor": payload.get("selected_factor"),
        "recommendation_status": metadata.get("recommendation_status"),
        "recommendation_output_label": metadata.get("recommendation_output_label"),
        "fresh_live_data_available": metadata.get("fresh_live_data_available"),
        "decision_support_tier": metadata.get("decision_support_tier"),
        "default_top_n": config.get("top_n", 20),
        "default_max_weight": config.get("max_weight", 0.1),
    }
    data_as_of = str(metadata.get("data_as_of") or metadata.get("run_timestamp_utc") or "unknown")[:10]
    holdings = []
    for rank, row in enumerate(rows[:50], start=1):
        holdings.append(
            {
                "date": data_as_of,
                "window": "latest",
                "window_label": "최신",
                "factor": payload.get("selected_factor"),
                "score_date": row.get("signal_date", data_as_of) if isinstance(row, dict) else data_as_of,
                "rank": row.get("rank", rank) if isinstance(row, dict) else rank,
                "symbol": row.get("symbol", "") if isinstance(row, dict) else "",
                "score": row.get("score") if isinstance(row, dict) else None,
                "default_weight": row.get("weight") if isinstance(row, dict) else None,
            }
        )
    selected_factor = payload.get("selected_factor")
    factor_leaders = [
        {
            "date": data_as_of,
            "window": "latest",
            "window_label": "최신",
            "best_factor": selected_factor,
            "best_return": None,
            "selected_factor": selected_factor,
            "selected_factor_return": None,
            "selected_factor_rank": 1 if selected_factor else None,
            "factor_count": 1 if selected_factor else 0,
        }
    ] if holdings else []
    return _json_safe(
        {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "source_json": str(path),
            "summary": summary,
            "periods": [{"key": "latest", "label": "최신", "trading_days": None}],
            "factor_leaders": factor_leaders,
            "factor_period_rankings": [],
            "holdings": holdings,
            "latest_output_rows": rows[:50],
            "notes_ko": ["이 파일은 legacy run-results JSON에서 만든 제한적 대시보드 payload입니다."],
        }
    )


def _expand_run_result_paths(patterns: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(patterns, str | Path):
        raw_patterns = [patterns]
    else:
        raw_patterns = list(patterns)
    paths: list[Path] = []
    for raw in raw_patterns:
        text = str(raw)
        matches = [Path(match) for match in glob(text)] if any(ch in text for ch in "*?[") else [Path(text)]
        paths.extend(matches)
    existing = sorted({path for path in paths if path.exists()})
    if not existing:
        raise ValueError("no run-results JSON files matched the provided path or glob")
    return existing


def _date_str(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _float_or_none(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value
