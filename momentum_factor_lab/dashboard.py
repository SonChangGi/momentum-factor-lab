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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .workflow import RunResult


DASHBOARD_PERIODS: dict[str, int] = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}

DASHBOARD_MAX_JSON_BYTES = 5_000_000
DASHBOARD_PAYLOAD_MAX_BYTES = 4_500_000
MAX_FACTOR_RANKINGS_PER_PERIOD = 100
MAX_SCORE_SNAPSHOT_DATES = 35
MAX_SCORE_SNAPSHOT_SYMBOLS = 50
MAX_BACKTEST_POINTS = 260

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
        최근 기간별 최고 팩터와 일별 상위 종목, 모멘텀 신호, 표시용 모형 비중을 한 화면에서 비교합니다.
      </p>
    </div>
    <div class="status-card" id="run-status">데이터를 불러오는 중...</div>
  </header>
  <noscript>
    <div class="noscript-warning">
      이 대시보드는 정적 JSON 데이터를 불러와 표와 차트를 그리므로 JavaScript가 필요합니다.
      JavaScript를 켠 뒤 다시 열어주세요.
    </div>
  </noscript>

  <main>
    <section class="notice">
      <strong>중요:</strong> 이 웹사이트의 선택값은 브라우저에서 비교/표시만 바꾸며,
      다음 자동 실행 설정을 저장하지 않습니다. 매일 실행 입력값은 저장소의
      <code>.github/momentum-dashboard-config.json</code>에서 관리됩니다.
      자동 실행은 GitHub Actions 예약 지연을 줄이기 위해 한국시간 08:17을 기본 실행 시각으로 두고,
      08:47·09:17 보강 실행은 당일 08:00 이후 이미 실행된 경우 자동으로 건너뜁니다.
    </section>

    <section class="manual-update" aria-label="수동 최신 데이터 업데이트">
      <div>
        <p class="eyebrow">수동 업데이트</p>
        <h2>오늘 기준 최신 데이터로 다시 실행</h2>
        <p>
          버튼을 누르면 이 저장소의 GitHub Actions 수동 실행 화면이 열립니다.
          저장소 쓰기 권한이 있는 GitHub 계정으로 로그인 후 <strong>Run workflow</strong>를 누르면
          <code>workflow_dispatch</code>가 실행되어 최신 무료 가격 데이터 수집, 팩터 백테스트,
          종목/비중 산출, <code>docs/data/dashboard.json</code> 갱신, GitHub Pages 배포까지
          같은 파이프라인으로 진행됩니다.
        </p>
        <p class="manual-update-note">
          보안상 공개 정적 페이지에는 GitHub 토큰을 저장하지 않습니다. 따라서 브라우저 버튼은
          인증된 GitHub 실행 화면으로 안전하게 연결하며, 자동 예약 실행은 기존대로 유지됩니다.
        </p>
      </div>
      <div class="manual-update-actions">
        <a id="manual-update-button" class="button primary" href="https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml" target="_blank" rel="noopener">GitHub Actions에서 최신 데이터 업데이트 실행</a>
        <button id="copy-update-command" class="button secondary" type="button">CLI 실행 명령 복사</button>
        <code id="manual-update-command" class="code-pill">gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main</code>
        <small id="manual-update-status" role="status" aria-live="polite">실행 후 변경사항이 있으면 새 JSON이 커밋되고 Pages가 갱신됩니다. Actions 상태와 대시보드 기준일을 확인하세요.</small>
      </div>
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
      <label>선택 팩터 시나리오
        <select id="factor-select"></select>
        <span class="control-hint">기간 최고 팩터와 별도로 비교할 표시용 팩터입니다.</span>
      </label>
      <label>상위 N개 표시
        <input id="topn-input" type="number" min="1" max="50" value="20" />
      </label>
      <label>브라우저 시나리오 종목당 최대 비중
        <input id="max-weight-input" type="number" min="1" max="50" step="1" value="10" />
        <span class="unit">%</span>
        <span class="control-hint">표시용 가정이며 자동 실행 설정을 저장하지 않습니다.</span>
      </label>
    </section>

    <section class="cards" aria-label="요약 카드">
      <article class="card">
        <span>선택된 최고 팩터</span>
        <strong id="best-factor">-</strong>
        <small id="best-factor-detail">-</small>
      </article>
      <article class="card">
        <span>선택 팩터 시나리오</span>
        <strong id="selected-factor">-</strong>
        <small id="selected-factor-detail">-</small>
      </article>
      <article class="card">
        <span>추천/신호 상태</span>
        <strong id="recommendation-status">-</strong>
        <small id="data-provider">-</small>
      </article>
      <article class="card">
        <span>최근 실행 시각</span>
        <strong id="latest-run-at">-</strong>
        <small id="latest-run-detail">-</small>
      </article>
      <article class="card">
        <span>시나리오 비중 합계</span>
        <strong id="weight-summary">-</strong>
        <small>브라우저에서 선택 팩터 점수와 최대 비중 가정으로 다시 계산한 표시용 목표 비중입니다.</small>
      </article>
    </section>

    <section class="panel diagnostics-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">현실성 점검</p>
          <h2>데이터 품질 · 유동성 · 매매 가능성 게이트</h2>
        </div>
        <p>
          현재 출력이 실제 매매 권고인지, 연구용 신호인지 판단하는 핵심 제한 조건을 한글로 풀어 표시합니다.
          후보 종목, 가격 적격, 유동성 적격 종목 수를 함께 확인하세요.
        </p>
      </div>
      <div class="diagnostic-grid">
        <article class="diagnostic-card">
          <h3>데이터 커버리지</h3>
          <dl id="data-quality-summary"></dl>
        </article>
        <article class="diagnostic-card">
          <h3>추천/신호 게이트</h3>
          <div id="tradability-gate-list" class="gate-list"></div>
        </article>
      </div>
    </section>

    <section class="panel diagnostics-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">팩터 해석</p>
          <h2>경제적 의미 · 중복도 · Forward Rank-IC</h2>
        </div>
        <p>
          현재 라이브러리는 가격 기반 모멘텀 팩터들의 변형입니다. 서로 비슷한 팩터가 많은지,
          신호가 이후 수익률과 어떤 순위 상관을 보였는지 진단합니다.
        </p>
      </div>
      <p id="factor-scope-note" class="diagnostic-note">-</p>
      <div class="diagnostic-grid three">
        <article class="diagnostic-card">
          <h3>팩터 카테고리</h3>
          <div id="factor-category-summary" class="mini-list"></div>
        </article>
        <article class="diagnostic-card">
          <h3>Forward Rank-IC 상위</h3>
          <div id="factor-rank-ic-summary" class="mini-list"></div>
        </article>
        <article class="diagnostic-card">
          <h3>팩터 중복도</h3>
          <div id="factor-redundancy-summary" class="mini-list"></div>
        </article>
      </div>
    </section>

    <section class="panel visual-panel" id="visual-dashboard">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">시각화 대시보드</p>
          <h2>팩터별 비교 · 백테스트 추이 · 상위 N개 비중</h2>
        </div>
        <p>
          위 입력값을 바꾸면 아래 차트가 즉시 갱신됩니다. 표보다 먼저 팩터별 상대 강도와
          선택 팩터 시나리오와 기간 최고 팩터를 분리해 빠르게 파악하도록 구성했습니다.
          임의 팩터/날짜 선택은 사후 비교 분석이며 새로 검증된 투자전략을 뜻하지 않습니다.
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
        <article class="viz-card wide">
          <div class="viz-card-heading">
            <div>
              <p class="eyebrow">백테스트 추이</p>
              <h3>선택 팩터와 기간 최고 팩터 누적 성과 비교</h3>
            </div>
            <span id="backtest-chart-meta" class="chart-meta">-</span>
          </div>
          <div id="backtest-chart" class="line-chart" aria-live="polite"></div>
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
              <p class="eyebrow">모형 비중</p>
              <h3>상위 N개 모형 비중 시각화</h3>
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
          <p class="eyebrow">최신 출력</p>
          <h2>기존 결과물 기준 최신 추천/연구 신호</h2>
        </div>
        <p>
          현재 실행에서 생성된 최신 추천 또는 연구 신호 행입니다.
          최종 비중이 0%라면 현재 실행이 연구용 신호로 분류되어 매매 권고를 막은 상태입니다.
          이 표는 브라우저 시나리오 비중과 별개로 기존 분석 코드가 생성한 최신 출력입니다.
        </p>
      </div>
      <div class="table-wrap">
        <table id="current-output-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>종목</th>
              <th>모멘텀 신호</th>
              <th>최종 비중</th>
              <th>사전 산출 비중</th>
              <th>비중 산출 방식</th>
              <th>신호일</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
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
              <th>선택 팩터 수익률</th>
              <th>선택 팩터 순위</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">선택 팩터 시나리오</p>
          <h2>일별 상위 종목 · 모멘텀 신호 · 산출 비중</h2>
        </div>
        <p id="holdings-availability">브라우저에서 선택 팩터 점수 스냅샷과 종목당 최대 비중 가정으로 표시용 목표 비중을 계산합니다.</p>
      </div>
      <div class="table-wrap">
        <table id="holdings-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>종목</th>
              <th>모멘텀 신호</th>
              <th>시나리오 목표 비중</th>
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
          <li><strong>기간 최고 팩터</strong>는 선택 기간의 과거 누적 수익률이 가장 높았던 팩터입니다.</li>
          <li><strong>선택 팩터 시나리오</strong>는 사용자가 고른 팩터의 점수 스냅샷으로 브라우저가 다시 계산한 표시용 비교입니다.</li>
          <li><strong>시나리오 목표 비중</strong>은 선택 팩터 점수가 높은 종목에 더 큰 비중을 주되 종목당 최대 비중을 넘지 않도록 계산하며, 상한 때문에 남는 금액은 현금/미사용으로 표시합니다.</li>
          <li>브라우저 입력값은 자동 실행 설정이나 GitHub Actions 입력값을 바꾸지 않습니다.</li>
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
body {
  margin: 0; background: var(--bg); color: var(--ink);
  word-break: keep-all; overflow-wrap: anywhere;
}
.hero {
  display: flex; justify-content: space-between; gap: 2rem; align-items: stretch;
  padding: 3rem clamp(1rem, 4vw, 4rem); color: white;
  background: linear-gradient(135deg, #132033 0%, #2457d6 72%, #44b3ff 100%);
}
.hero > * { min-width: 0; }
.hero h1 { margin: .25rem 0 1rem; font-size: clamp(2rem, 5vw, 4rem); }
.hero-copy { max-width: 760px; line-height: 1.7; opacity: .92; }
.eyebrow { margin: 0 0 .35rem; color: var(--accent); font-weight: 800; letter-spacing: .035em; font-size: .78rem; line-height: 1.45; }
.hero .eyebrow { color: #c7dcff; }
.status-card { min-width: 300px; align-self: center; border: 1px solid rgba(255,255,255,.32); border-radius: 24px; padding: 1.25rem; background: rgba(255,255,255,.14); backdrop-filter: blur(8px); line-height: 1.6; }
.status-card.is-updating { outline: 2px solid rgba(255,255,255,.56); }
.status-card.is-updating::after { content: " · 처리 중"; font-weight: 800; }
.status-line { display: grid; grid-template-columns: 7.2rem minmax(0, 1fr); gap: .65rem; align-items: start; }
.status-line + .status-line { margin-top: .35rem; }
.status-label { color: #dce9ff; font-weight: 800; }
.status-value { overflow-wrap: anywhere; }
main { padding: 1.5rem clamp(1rem, 4vw, 4rem) 3rem; }
.notice, .panel, .disclaimer, .controls, .card { background: var(--panel); border: 1px solid var(--line); box-shadow: 0 12px 30px rgba(15, 23, 42, .06); }
.notice { padding: 1rem 1.25rem; border-radius: 18px; margin-bottom: 1.25rem; color: #334155; }
.manual-update {
  display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, .6fr); gap: 1rem; align-items: center;
  padding: 1.25rem; border-radius: 22px; margin-bottom: 1.25rem;
  background: linear-gradient(135deg, #ffffff 0%, #eef5ff 100%); border: 1px solid var(--line); box-shadow: 0 12px 30px rgba(15, 23, 42, .06);
}
.manual-update h2 { margin: 0 0 .65rem; }
.manual-update p { margin: 0; color: #334155; line-height: 1.7; }
.manual-update p + p { margin-top: .55rem; }
.manual-update-note { font-size: .92rem; color: var(--muted); }
.manual-update-actions { display: grid; gap: .65rem; justify-items: stretch; }
.button {
  display: inline-flex; justify-content: center; align-items: center; min-height: 2.75rem;
  border-radius: 14px; border: 1px solid transparent; padding: .7rem 1rem; font: inherit; font-weight: 900; cursor: pointer; text-decoration: none;
}
.button.primary { color: #fff; background: var(--accent); box-shadow: 0 12px 22px rgba(36, 87, 214, .24); }
.button.primary:hover { background: #1d4ed8; }
.button.secondary { color: var(--accent); background: #fff; border-color: #bfd0ff; }
.button.secondary:hover { background: #f8fbff; }
.code-pill { display: block; padding: .75rem .85rem; border-radius: 14px; background: #132033; color: #e8efff; font-size: .82rem; line-height: 1.45; overflow-wrap: anywhere; }
#manual-update-status { color: var(--muted); line-height: 1.5; }
.noscript-warning { margin: 1rem clamp(1rem, 4vw, 4rem); padding: 1rem 1.25rem; border-radius: 18px; background: #fff4e6; color: #8a4b00; border: 1px solid #ffd8a8; font-weight: 800; line-height: 1.6; }
.controls { display: grid; grid-template-columns: repeat(6, minmax(150px, 1fr)); gap: 1rem; padding: 1rem; border-radius: 22px; margin-bottom: 1.25rem; }
label { font-size: .86rem; color: var(--muted); font-weight: 700; display: flex; flex-direction: column; gap: .45rem; position: relative; }
select, input { width: 100%; border: 1px solid var(--line); border-radius: 12px; padding: .72rem .8rem; color: var(--ink); background: #fff; font: inherit; }
input[readonly] { background: #f8fafc; color: var(--muted); }
.unit { position: absolute; right: .8rem; top: 2.25rem; color: var(--muted); }
.control-hint { color: var(--muted); font-size: .72rem; line-height: 1.35; font-weight: 600; overflow-wrap: anywhere; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; margin-bottom: 1.25rem; }
.card { border-radius: 22px; padding: 1.1rem; }
.card span { color: var(--muted); font-weight: 700; font-size: .85rem; }
.card strong { display: block; margin: .45rem 0; font-size: clamp(1.05rem, 2vw, 1.35rem); line-height: 1.25; overflow-wrap: anywhere; }
.card small { color: var(--muted); line-height: 1.5; }
.panel { border-radius: 26px; padding: 1.25rem; margin-bottom: 1.25rem; }
.panel-heading { display: flex; justify-content: space-between; gap: 1.5rem; align-items: end; margin-bottom: 1rem; }
.panel-heading h2, .explain h2, .disclaimer h2 { margin: 0; }
.panel-heading p { margin: 0; color: var(--muted); max-width: 620px; line-height: 1.6; }
.table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 18px; }
table { width: 100%; border-collapse: collapse; min-width: 760px; background: #fff; table-layout: auto; }
th, td { text-align: left; padding: .78rem .9rem; border-bottom: 1px solid var(--line); white-space: normal; overflow-wrap: anywhere; vertical-align: top; }
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
.diagnostic-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.diagnostic-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.diagnostic-card { border: 1px solid var(--line); border-radius: 20px; padding: 1rem; background: #fff; min-width: 0; }
.diagnostic-card h3 { margin: 0 0 .8rem; font-size: 1rem; }
.diagnostic-card dl { display: grid; grid-template-columns: minmax(110px, .7fr) minmax(0, 1fr); gap: .55rem .85rem; margin: 0; }
.diagnostic-card dt { color: var(--muted); font-weight: 800; }
.diagnostic-card dd { margin: 0; font-weight: 800; overflow-wrap: anywhere; }
.diagnostic-note { margin-top: -0.25rem; color: #334155; background: #f8fafc; border: 1px solid var(--line); border-radius: 16px; padding: .85rem 1rem; line-height: 1.6; }
.gate-list, .mini-list { display: grid; gap: .6rem; }
.gate-item, .mini-item { border: 1px solid var(--line); border-radius: 16px; padding: .75rem; background: #f8fafc; line-height: 1.45; }
.gate-item.pass { border-color: #b7ebd5; background: #effcf7; }
.gate-item.block { border-color: #ffd8a8; background: #fff8ef; }
.gate-item strong, .mini-item strong { display: block; margin-bottom: .25rem; overflow-wrap: anywhere; }
.gate-item small, .mini-item small { color: var(--muted); }
.viz-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.viz-card {
  border: 1px solid var(--line); border-radius: 22px; padding: 1rem;
  background: rgba(255,255,255,.86); box-shadow: 0 10px 24px rgba(15, 23, 42, .05);
}
.viz-card.wide { grid-column: 1 / -1; }
.viz-card-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; margin-bottom: .9rem; }
.viz-card h3 { margin: 0; font-size: 1.05rem; }
.chart-meta { color: var(--muted); font-size: .82rem; font-weight: 800; text-align: right; line-height: 1.4; }
.bar-chart { display: grid; gap: .62rem; }
.bar-row { display: grid; grid-template-columns: minmax(0, .9fr) minmax(140px, 2fr) 88px; gap: .75rem; align-items: center; }
.bar-row.is-selected { padding: .35rem; border: 1px solid #b7c9ff; border-radius: 14px; background: #f2f6ff; }
.bar-row.is-best:not(.is-selected) { padding: .35rem; border: 1px solid #b7ebd5; border-radius: 14px; background: #effcf7; }
.bar-label { font-weight: 800; overflow-wrap: anywhere; line-height: 1.35; }
.bar-track { height: 12px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.bar-fill { height: 100%; width: var(--bar-width, 0%); border-radius: inherit; background: linear-gradient(90deg, var(--accent), #44b3ff); }
.bar-fill.negative { background: linear-gradient(90deg, #f03e3e, #ff8787); }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; font-weight: 800; }
.compact-bars .bar-row { grid-template-columns: minmax(0, .55fr) minmax(120px, 1.6fr) 76px; }
.window-chart { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.window-chip { border: 1px solid var(--line); border-radius: 18px; padding: .85rem; background: #fff; }
.window-chip span { display: block; color: var(--muted); font-size: .78rem; font-weight: 800; }
.window-chip strong { display: block; margin: .35rem 0; font-size: 1.05rem; overflow-wrap: anywhere; }
.window-chip small { color: var(--muted); line-height: 1.45; }
.trend-chart { min-height: 220px; }
.trend-bars { display: flex; gap: .35rem; align-items: end; height: 180px; padding: .75rem .35rem .25rem; border: 1px solid var(--line); border-radius: 18px; background: #fff; overflow-x: auto; }
.trend-bar { display: flex; flex-direction: column; align-items: center; justify-content: end; min-width: 28px; height: 100%; gap: .35rem; }
.trend-fill { width: 18px; height: var(--bar-height, 0%); min-height: 3px; border-radius: 999px 999px 4px 4px; background: linear-gradient(180deg, #44b3ff, var(--accent)); }
.trend-fill.negative { background: linear-gradient(180deg, #ff8787, #f03e3e); }
.trend-label { color: var(--muted); font-size: .68rem; writing-mode: vertical-rl; max-height: 46px; overflow: hidden; }
.line-chart { min-height: 260px; border: 1px solid var(--line); border-radius: 18px; background: #fff; padding: .85rem; }
.line-chart svg { display: block; width: 100%; height: 220px; overflow: visible; }
.line-grid { stroke: #e2e8f0; stroke-width: 1; }
.line-path { fill: none; stroke-width: 2.8; stroke-linecap: round; stroke-linejoin: round; }
.line-path.selected { stroke: var(--accent); }
.line-path.best { stroke: var(--good); stroke-dasharray: 5 5; }
.line-legend { display: flex; flex-wrap: wrap; gap: .7rem; margin-top: .75rem; color: #334155; font-size: .84rem; line-height: 1.45; }
.legend-dot { display: inline-block; width: .7rem; height: .7rem; border-radius: 50%; margin-right: .35rem; vertical-align: -.05rem; background: var(--accent); }
.legend-dot.best { background: var(--good); }
.scenario-note { margin-top: .75rem; color: #334155; background: #f8fafc; border: 1px solid var(--line); border-radius: 16px; padding: .75rem; line-height: 1.55; font-size: .9rem; }
.empty-state { color: var(--muted); border: 1px dashed var(--line); border-radius: 18px; padding: 1rem; background: #fff; line-height: 1.6; }
footer { display: flex; justify-content: space-between; gap: 1rem; color: var(--muted); padding: 1.5rem clamp(1rem, 4vw, 4rem); }
@media (max-width: 980px) {
  .hero, .panel-heading, footer { flex-direction: column; }
  .controls, .manual-update, .cards, .two-col, .viz-grid, .window-chart, .diagnostic-grid, .diagnostic-grid.three { grid-template-columns: 1fr; }
  .bar-row, .compact-bars .bar-row { grid-template-columns: 1fr; gap: .35rem; }
  .bar-value { text-align: left; }
  .status-card { width: 100%; }
}
"""


JS_CONTENT = """const MANUAL_UPDATE_WORKFLOW_URL = 'https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml';
const MANUAL_UPDATE_COMMAND = 'gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main';

const state = {
  data: null,
  activeRunIndex: 0,
};

function bindManualUpdateControls() {
  const button = document.querySelector('#manual-update-button');
  if (button) {
    button.setAttribute('href', MANUAL_UPDATE_WORKFLOW_URL);
    button.setAttribute('target', '_blank');
    button.setAttribute('rel', 'noopener');
    if (typeof button.addEventListener === 'function') {
      button.addEventListener('click', () => {
        const status = document.querySelector('#manual-update-status');
        if (status) {
          status.textContent = '저장소 쓰기 권한이 있는 GitHub 계정으로 Run workflow를 눌러 최신 데이터 재실행을 시작하세요.';
        }
      });
    }
  }

  const command = document.querySelector('#manual-update-command');
  if (command) command.textContent = MANUAL_UPDATE_COMMAND;

  const copyButton = document.querySelector('#copy-update-command');
  if (!copyButton || typeof copyButton.addEventListener !== 'function') return;
  copyButton.addEventListener('click', async () => {
    const status = document.querySelector('#manual-update-status');
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard || !window.isSecureContext) {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(MANUAL_UPDATE_COMMAND);
      if (status) status.textContent = 'CLI 실행 명령을 복사했습니다. 터미널에서 붙여넣어 수동 실행할 수 있습니다.';
    } catch (_) {
      if (status) status.textContent = `복사가 제한되었습니다. 아래 명령을 직접 복사하세요: ${MANUAL_UPDATE_COMMAND}`;
    }
  });
}

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 4 });
};

const formatInteger = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: 0 });
};

const formatCount = (value) => {
  const formatted = formatInteger(value);
  return formatted === '-' ? '-' : `${formatted}개`;
};

const classForNumber = (value) => Number(value) >= 0 ? 'positive' : 'negative';
const textValue = (value) => value === null || value === undefined ? '-' : String(value);

function formatKoreanDateTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return textValue(value);
  return `${date.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })} KST`;
}

function humanProvider(value) {
  const text = textValue(value);
  const labels = {
    'yfinance-free-public-data': '야후 파이낸스 무료 공개 데이터',
    'stooq-fallback': 'Stooq 무료 일별 종가 대체 데이터',
    'finance-datareader-fallback': 'FinanceDataReader 무료 종가 대체 데이터',
    'no-live-price-provider': '사용 가능한 실시간 가격 제공자 없음',
    'offline-sample': '오프라인 샘플 데이터',
    'offline_sample': '오프라인 샘플 데이터',
  };
  if (text.includes('+')) {
    return text.split('+').map((part) => labels[part] || `기타 제공자(${part})`).join(' + ');
  }
  return labels[text] || text;
}

function humanOutputLabel(value) {
  const text = textValue(value);
  const labels = {
    'Research signals (not tradable)': '연구용 신호(매매 권고 아님)',
    'Practical recommendations': '실행 가능성 검토를 통과한 추천 후보',
    'No current recommendation': '현재 추천 후보 없음',
  };
  return labels[text] || text;
}

function humanStatus(status, outputLabel) {
  const text = textValue(status);
  if (text === '-') return humanOutputLabel(outputLabel);
  if (text === 'sample_offline_not_current') {
    return '오프라인 샘플 · 현재 추천 아님';
  }
  if (text === 'current_live') {
    return '최신 데이터 · 실행 가능성 점검 통과';
  }
  if (text.includes('subset')) {
    return '일부 종목 실행 · 연구용 신호';
  }
  if (text.includes('with_limitations')) {
    return '최신 데이터 · 제한 조건 때문에 연구용 신호';
  }
  if (text.includes('research') || String(outputLabel || '').includes('Research signals')) {
    return '현재 데이터 사용 · 연구용 신호 · 매매 권고 아님';
  }
  if (text.includes('pass')) {
    return '현재 데이터 사용 · 품질 점검 통과';
  }
  if (text.includes('stale')) {
    return '데이터가 최신이 아닐 수 있음';
  }
  if (text.includes('fail') || text.includes('blocked')) {
    return '제한 조건 때문에 추천 보류';
  }
  return text;
}

function isPracticalRun(run = currentRun()) {
  const summary = run.summary || {};
  return String(summary.recommendation_output_label || '').includes('Practical')
    || String(summary.recommendation_status || '') === 'current_live';
}

function humanFactorCategory(value) {
  const text = textValue(value);
  const labels = {
    traditional: '전통 모멘텀',
    recent: '최근 수익률',
    composite: '복합 모멘텀',
    risk_adjusted: '위험조정 모멘텀',
    trend: '추세/이동평균',
    drawdown: '낙폭/고점 근접',
    breakout: '돌파',
    reversal: '반전 보정',
    acceleration: '가속도',
    quality: '추세 품질',
    cross_sectional: '횡단면 상대강도',
    robust: '이상치 완화',
    range: '가격 범위 위치',
    unknown: '분류 정보 없음',
  };
  return labels[text] || `기타(${text})`;
}

function humanWeightingMethod(value) {
  const text = textValue(value);
  const labels = {
    equal: '동일 비중',
    score_size_liquidity: '점수·규모·유동성 기반',
  };
  return labels[text] || text;
}

function currentRun() {
  const runs = state.data?.runs || [];
  return runs[state.activeRunIndex] || runs[state.data?.latest_run_index || 0] || state.data?.latest || {};
}

function runPayloadGeneratedAt(run) {
  return run?.generated_at_utc || state.data?.generated_at_utc || null;
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

function selectedFactor() {
  const selector = document.querySelector('#factor-select');
  return selector?.value || currentRun().summary?.selected_factor || '';
}

function clampNumber(value, minValue, maxValue, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minValue, Math.min(maxValue, parsed));
}

function optionalNumber(value) {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampedTopN() {
  return Math.round(clampNumber(document.querySelector('#topn-input').value, 1, 50, 20));
}

function clampedMaxWeight() {
  const percent = clampNumber(document.querySelector('#max-weight-input').value, 1, 50, 10);
  const input = document.querySelector('#max-weight-input');
  if (String(input.value) !== String(percent)) input.value = String(percent);
  return percent / 100;
}

function factorOptions(run = currentRun()) {
  const options = run.factor_options || [];
  if (options.length) return options;
  const factors = [...new Set([
    run.summary?.selected_factor,
    ...(run.factor_leaders || []).map((row) => row.best_factor),
    ...(run.factor_period_rankings || []).map((row) => row.factor),
  ].filter(Boolean))].sort();
  return factors.map((factor) => ({ factor, category: 'unknown', description_ko: '팩터 설명 정보가 없습니다.' }));
}

function factorDescription(factor, run = currentRun()) {
  const option = factorOptions(run).find((item) => item.factor === factor);
  if (!option) return '팩터 설명 정보가 없습니다.';
  const category = humanFactorCategory(option.category);
  const description = option.description_ko || option.description || '설명 정보가 없습니다.';
  return `${category} · ${description}`;
}

function periodMatrixEntry(run, date, windowKey) {
  return (run.factor_period_matrix || []).find((row) => row.date === date && row.window === windowKey) || null;
}

function periodFactorStats(run, date, windowKey, factor) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    const index = matrix.factors.indexOf(factor);
    if (index >= 0) {
      return {
        factor,
        rank: index + 1,
        period_return: optionalNumber(matrix.returns?.[index]),
        factor_count: matrix.factors.length,
        window_label: matrix.window_label || windowKey,
      };
    }
    return {
      factor,
      rank: null,
      period_return: null,
      factor_count: matrix.factors.length,
      window_label: matrix.window_label || windowKey,
    };
  }
  const row = (run.factor_period_rankings || []).find((item) => (
    item.date === date && item.window === windowKey && item.factor === factor
  ));
  if (!row) return null;
  return { ...row, rank: row.rank, factor_count: row.factor_count || null };
}

function periodBestStats(run, date, windowKey) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors) && matrix.factors.length) {
    return {
      factor: matrix.factors[0],
      rank: 1,
      period_return: optionalNumber(matrix.returns?.[0]),
      factor_count: matrix.factors.length,
      window_label: matrix.window_label || windowKey,
    };
  }
  const leader = (run.factor_leaders || []).find((item) => item.date === date && item.window === windowKey);
  if (!leader) return null;
  return {
    factor: leader.best_factor,
    rank: 1,
    period_return: leader.best_return,
    factor_count: leader.factor_count,
    window_label: leader.window_label || windowKey,
  };
}

function factorScoreSnapshot(run, date, factor) {
  return (run.factor_score_snapshots || []).find((snapshot) => snapshot.date === date && snapshot.factor === factor) || null;
}

function normalizeSnapshotRows(snapshot) {
  const rows = snapshot?.rows || [];
  return rows
    .map((row) => {
      if (Array.isArray(row)) return { symbol: row[0], score: Number(row[1]) };
      return { symbol: row.symbol, score: Number(row.score) };
    })
    .filter((row) => row.symbol && Number.isFinite(row.score))
    .sort((a, b) => Number(b.score) - Number(a.score) || String(a.symbol).localeCompare(String(b.symbol)));
}

function computeScenarioAllocation(rows, topN, maxWeight) {
  const safeRows = normalizeSnapshotRows({ rows });
  const count = Math.max(1, Math.min(50, Math.round(Number(topN) || 20), safeRows.length || 1));
  const cap = Math.max(0.01, Math.min(0.5, Number(maxWeight) || 0.1));
  const selected = safeRows.slice(0, count);
  const scores = selected.map((row) => Number(row.score) || 0);
  const minScore = scores.length ? Math.min(...scores) : 0;
  const maxScore = scores.length ? Math.max(...scores) : 0;
  const scoreRange = maxScore - minScore;
  const rawScores = scoreRange > 0
    ? scores.map((score) => score - minScore + Math.max(scoreRange * 1e-6, 1e-9))
    : selected.map((_, index) => selected.length - index);
  const weights = Array(selected.length).fill(0);
  const remainingIndexes = new Set(selected.map((_, index) => index));
  let remainingBudget = 1;
  while (remainingIndexes.size && remainingBudget > 1e-12) {
    const activeRawTotal = [...remainingIndexes].reduce((sum, index) => sum + rawScores[index], 0);
    if (activeRawTotal <= 0) break;
    const cappedThisRound = [];
    for (const index of remainingIndexes) {
      const candidateWeight = remainingBudget * (rawScores[index] / activeRawTotal);
      if (candidateWeight > cap) {
        weights[index] = cap;
        cappedThisRound.push(index);
      }
    }
    if (!cappedThisRound.length) {
      for (const index of remainingIndexes) {
        weights[index] = remainingBudget * (rawScores[index] / activeRawTotal);
      }
      remainingBudget = 0;
      break;
    }
    cappedThisRound.forEach((index) => {
      remainingIndexes.delete(index);
      remainingBudget -= weights[index];
    });
  }
  const weighted = selected.map((row, index) => ({
    ...row,
    display_rank: index + 1,
    display_weight: Math.max(0, weights[index] || 0),
    scenario_weight: Math.max(0, weights[index] || 0),
  }));
  const investedTotal = weighted.reduce((sum, row) => sum + row.display_weight, 0);
  return {
    weighted,
    investedTotal,
    displayedTotal: investedTotal,
    portfolioTotal: investedTotal,
    cashTotal: Math.max(0, 1 - investedTotal),
    unusedCandidateCount: Math.max(0, safeRows.length - weighted.length),
    weightingMethod: 'score_proportional_capped',
    topN: count,
    maxWeight: cap,
    availableCount: safeRows.length,
  };
}

function setText(selector, value) {
  document.querySelector(selector).textContent = textValue(value);
}

function appendDefinition(target, label, value) {
  const dt = document.createElement('dt');
  dt.textContent = label;
  const dd = document.createElement('dd');
  dd.textContent = textValue(value);
  target.append(dt, dd);
}

function formatCounts(counts, labels = {}) {
  if (!counts || typeof counts !== 'object' || Array.isArray(counts)) return '-';
  const entries = Object.entries(counts).filter(([, value]) => Number(value) > 0);
  if (!entries.length) return '-';
  return entries
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([key, value]) => `${labels[key] || key} ${formatInteger(value)}`)
    .join(' · ');
}

function setStatusMessage(message) {
  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  statusCard.textContent = message;
  statusCard.setAttribute('aria-busy', 'true');
  statusCard.classList.add('is-updating');
}

function appendStatusLine(target, label, value) {
  const row = document.createElement('div');
  row.className = 'status-line';
  const labelNode = document.createElement('span');
  labelNode.className = 'status-label';
  labelNode.textContent = label;
  const valueNode = document.createElement('span');
  valueNode.className = 'status-value';
  valueNode.textContent = textValue(value);
  row.append(labelNode, valueNode);
  target.appendChild(row);
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
  const factor = selectedFactor();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const snapshot = factorScoreSnapshot(run, date, factor);
  const availableDates = run.scenario_available_dates || [];
  const allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  const stats = periodFactorStats(run, date, windowKey, factor);
  return {
    ...allocation,
    snapshot,
    selectedFactor: factor || '-',
    windowLabel: stats?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
    scoreDate: snapshot?.score_date || null,
    missingReason: snapshot
      ? null
      : availableDates.length && !availableDates.includes(date)
      ? '선택한 기준일은 용량과 로딩 속도 제한 때문에 종목/비중 스냅샷 보관 범위 밖입니다.'
      : '선택한 기준일에 이 팩터의 점수 스냅샷이 없습니다.',
  };
}

function appendBarRow(target, label, valueLabel, value, maxAbs, options = {}) {
  const row = document.createElement('div');
  row.className = `bar-row ${options.className || ''}`.trim();

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

function factorAvailableDates(run, factor) {
  const byFactor = run.scenario_available_dates_by_factor || {};
  const dates = byFactor[factor] || run.scenario_available_dates || [];
  return new Set(dates);
}

function fillDateOptions(run, preferredDate = null) {
  const dates = uniqueDates(run);
  const availableDates = factorAvailableDates(run, selectedFactor());
  const dateSelect = document.querySelector('#date-select');
  dateSelect.replaceChildren();
  dates.forEach((date) => {
    const option = document.createElement('option');
    option.value = date;
    option.textContent = availableDates.has(date) ? `${date} · 종목/비중 가능` : `${date} · 팩터 수익률만`;
    dateSelect.appendChild(option);
  });
  if (dates.length) {
    dateSelect.value = preferredDate && dates.includes(preferredDate) ? preferredDate : dates[0];
  }
}

function fillControls() {
  const runSelect = document.querySelector('#run-select');
  runSelect.replaceChildren();
  const runs = state.data.runs || [];
  runs.forEach((run, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const prefix = runs.length <= 1 ? '최신 실행만 표시' : `실행 ${index + 1}`;
    option.textContent = `${prefix} · 기준일 ${run.summary?.data_as_of || '알 수 없음'} · 실행 ${formatKoreanDateTime(run.summary?.run_timestamp_utc)} · ${run.summary?.selected_factor || '-'}`;
    runSelect.appendChild(option);
  });
  runSelect.value = String(state.activeRunIndex);
  runSelect.disabled = runs.length <= 1;

  const run = currentRun();
  const previousFactor = document.querySelector('#factor-select')?.value || run.summary?.selected_factor || '';
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

  const factorSelect = document.querySelector('#factor-select');
  const previousDate = document.querySelector('#date-select')?.value || null;
  factorSelect.replaceChildren();
  const options = factorOptions(run);
  options.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.factor;
    option.textContent = item.factor === run.summary?.selected_factor
      ? `${item.factor} · 현재 실행 선택`
      : `${item.factor} · ${humanFactorCategory(item.category)}`;
    factorSelect.appendChild(option);
  });
  const factors = options.map((item) => item.factor);
  factorSelect.value = factors.includes(previousFactor)
    ? previousFactor
    : (factors.includes(run.summary?.selected_factor) ? run.summary.selected_factor : factors[0] || '');

  fillDateOptions(run, previousDate);
  document.querySelector('#topn-input').value = run.summary?.default_top_n || 20;
  document.querySelector('#max-weight-input').value = Math.round((run.summary?.default_max_weight || 0.1) * 100);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const best = periodBestStats(run, date, windowKey);
  const factor = selectedFactor();
  const selectedStats = periodFactorStats(run, date, windowKey, factor);
  const summary = run.summary || {};
  const latestRunAt = formatKoreanDateTime(summary.run_timestamp_utc);
  const runPayloadGeneratedAtText = formatKoreanDateTime(runPayloadGeneratedAt(run));
  setText('#best-factor', best?.factor || '-');
  setText('#best-factor-detail', best ? `${best.window_label} 수익률 ${formatPercent(best.period_return)}` : '-');
  setText('#selected-factor', factor || '-');
  setText(
    '#selected-factor-detail',
    selectedStats && selectedStats.rank
      ? `${selectedStats.window_label} 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'} · ${formatPercent(selectedStats.period_return)} · ${factorDescription(factor, run)}`
      : `자료 없음 · ${factorDescription(factor, run)}`,
  );
  setText('#recommendation-status', humanStatus(summary.recommendation_status, summary.recommendation_output_label));
  setText('#data-provider', `기준일 ${summary.data_as_of || '-'} · ${humanProvider(summary.provider)}`);
  setText('#latest-run-at', latestRunAt);
  setText('#latest-run-detail', `분석 실행 기준 · 실행 결과 생성 ${runPayloadGeneratedAtText}`);

  const statusCard = document.querySelector('#run-status');
  statusCard.replaceChildren();
  statusCard.removeAttribute('aria-busy');
  statusCard.classList.remove('is-updating');
  appendStatusLine(statusCard, '데이터 기준일', summary.data_as_of || '-');
  appendStatusLine(statusCard, '최근 실행', latestRunAt);
  appendStatusLine(statusCard, '실행 결과 생성', runPayloadGeneratedAtText);
  appendStatusLine(statusCard, '데이터 제공자', humanProvider(summary.provider));
  appendStatusLine(statusCard, '신호 상태', humanOutputLabel(summary.recommendation_output_label));

  setText('#generated-at', `사이트 빌드 시각: ${formatKoreanDateTime(state.data.generated_at_utc)}`);
}

function renderDiagnostics() {
  const run = currentRun();
  const summary = run.summary || {};
  const quality = run.data_quality_summary || {};
  const dataSummary = document.querySelector('#data-quality-summary');
  dataSummary.replaceChildren();
  appendDefinition(dataSummary, '후보 종목', formatCount(summary.candidate_universe_size ?? quality.candidate_universe_size));
  appendDefinition(dataSummary, '가격 적격 종목', formatCount(summary.eligible_price_universe_size ?? quality.eligible_price_universe_size));
  appendDefinition(dataSummary, '유동성 적격 종목', formatCount(summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size));
  appendDefinition(dataSummary, '가격 수집 종목', formatCount(quality.fetched_price_symbol_count));
  appendDefinition(dataSummary, '제외 종목 수', formatCount(quality.excluded_symbols));
  appendDefinition(dataSummary, '데이터 기준일', quality.data_as_of || summary.data_as_of || '-');
  appendDefinition(dataSummary, '최근 실행 시각', formatKoreanDateTime(summary.run_timestamp_utc));
  appendDefinition(dataSummary, '실행 결과 생성 시각', formatKoreanDateTime(runPayloadGeneratedAt(run)));
  appendDefinition(dataSummary, '가격 제공자', humanProvider(quality.provider || summary.provider));
  appendDefinition(
    dataSummary,
    '품질 상태',
    formatCounts(quality.data_quality_status_counts, {
      pass: '통과',
      missing_price: '가격 누락',
      missing_volume: '거래량 누락',
      provider_adjustment_incompatible: '조정가격 불일치',
      stale_price: '오래된 가격',
      insufficient_history: '이력 부족',
      below_liquidity_floor: '유동성 부족',
      benchmark_comparator_only: '벤치마크 전용',
    }),
  );
  appendDefinition(dataSummary, '유동성 상태', formatCounts(quality.liquidity_status_counts, { pass: '통과', fail: '미통과' }));
  appendDefinition(dataSummary, '용량 상태', formatCounts(quality.capacity_status_counts, { pass: '통과', fail: '미통과' }));

  const gateTarget = document.querySelector('#tradability-gate-list');
  gateTarget.replaceChildren();
  const gates = run.tradability_gate || [];
  if (!gates.length) {
    appendEmpty('#tradability-gate-list', '추천/신호 게이트 정보가 없습니다.');
  } else {
    gates.forEach((gate) => {
      const item = document.createElement('div');
      item.className = `gate-item ${gate.passed ? 'pass' : 'block'}`;
      const title = document.createElement('strong');
      title.textContent = `${gate.passed ? '통과' : '점검 필요'} · ${gate.label_ko || gate.key}`;
      const detail = document.createElement('small');
      detail.textContent = gate.description_ko || '추가 실행 가능성 점검 항목입니다.';
      item.append(title, detail);
      gateTarget.appendChild(item);
    });
  }

  const diagnostics = run.factor_diagnostics || {};
  setText('#factor-scope-note', diagnostics.scope_note_ko || '팩터 진단 정보가 없습니다.');

  const categoryTarget = document.querySelector('#factor-category-summary');
  categoryTarget.replaceChildren();
  const categories = diagnostics.category_summary || [];
  if (!categories.length) {
    appendEmpty('#factor-category-summary', '팩터 카테고리 요약이 없습니다.');
  } else {
    categories.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = `${humanFactorCategory(row.category)} · ${formatInteger(row.factor_count)}개`;
      const detail = document.createElement('small');
      detail.textContent = `평균 Rank-IC ${formatNumber(row.avg_mean_rank_ic)} · 양수 비율 ${formatPercent(row.avg_positive_ic_rate)} · 예: ${row.example_factors || '-'}`;
      item.append(title, detail);
      categoryTarget.appendChild(item);
    });
  }

  const icTarget = document.querySelector('#factor-rank-ic-summary');
  icTarget.replaceChildren();
  const rankIcRows = diagnostics.rank_ic_top || [];
  if (!rankIcRows.length) {
    appendEmpty('#factor-rank-ic-summary', 'Forward Rank-IC 진단이 없습니다.');
  } else {
    rankIcRows.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = row.factor || '-';
      const detail = document.createElement('small');
      detail.textContent = `${formatInteger(row.horizon_days ?? diagnostics.rank_ic_horizon_days)}거래일 후 Rank-IC ${formatNumber(row.mean_rank_ic)} · 관측 ${formatInteger(row.observations)}회 · 양수 비율 ${formatPercent(row.positive_ic_rate)} · 중첩 일별 관측`;
      item.append(title, detail);
      icTarget.appendChild(item);
    });
  }

  const redundancyTarget = document.querySelector('#factor-redundancy-summary');
  redundancyTarget.replaceChildren();
  const redundancyRows = diagnostics.redundancy_top || [];
  if (!redundancyRows.length) {
    appendEmpty('#factor-redundancy-summary', '팩터 중복도 진단이 없습니다.');
  } else {
    redundancyRows.slice(0, 8).forEach((row) => {
      const item = document.createElement('div');
      item.className = 'mini-item';
      const title = document.createElement('strong');
      title.textContent = `${row.factor || '-'} ↔ ${row.nearest_factor || '-'}`;
      const detail = document.createElement('small');
      detail.textContent = `순위상관 ${formatNumber(row.signed_rank_corr)} · 높은 상관 피어 ${formatInteger(row.high_corr_peer_count)}개 · 진단일 ${row.diagnostic_date || '-'}`;
      item.append(title, detail);
      redundancyTarget.appendChild(item);
    });
  }
}

function renderFactorTable() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const selectedStats = periodFactorStats(run, row.date, row.window, factor);
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, row.best_factor);
    appendCell(tr, formatPercent(row.best_return), { className: classForNumber(row.best_return) });
    appendCell(tr, selectedStats?.period_return == null ? '자료 없음' : formatPercent(selectedStats.period_return), { className: classForNumber(selectedStats?.period_return) });
    appendCell(tr, selectedStats?.rank ? `${selectedStats.rank}/${selectedStats.factor_count || '-'}` : '자료 없음');
    tbody.appendChild(tr);
  });
}

function renderHoldingsTable() {
  const run = currentRun();
  const {
    weighted,
    displayedTotal,
    portfolioTotal,
    cashTotal,
    topN,
    availableCount,
    selectedFactor: factor,
    windowLabel,
    scoreDate,
    unusedCandidateCount,
    maxWeight,
    missingReason,
  } = currentWeightedHoldings();
  const weightLabel = isPracticalRun(run) ? '표시용 투자 시나리오 비중' : '표시용 연구 시나리오 비중';
  setText(
    '#weight-summary',
    `시나리오 배분 ${formatPercent(portfolioTotal)} · 화면 표시 ${formatPercent(displayedTotal)} · 현금/미사용 ${formatPercent(cashTotal)}`,
  );
  const capNote = topN * maxWeight < 1
    ? `종목 수와 최대 비중 가정상 ${formatPercent(cashTotal)}는 현금/미사용으로 남습니다.`
    : '선택한 종목 수와 최대 비중 가정으로 100% 배분이 가능합니다.';
  setText(
    '#holdings-availability',
    missingReason
      ? `${missingReason} 기간 최고 팩터 보유를 대신 보여주지 않습니다.`
      : run.history_payload_type === 'summary'
      ? '이전 실행은 페이지 속도를 위해 요약 이력만 보관합니다. 상위 종목과 비중은 최신 실행에서 전체 표시됩니다.'
      : `${windowLabel} 선택 팩터 ${factor}의 ${scoreDate || '최근'} 점수 스냅샷 기준입니다. 전체 ${formatInteger(availableCount)}개 후보 중 상위 ${Math.min(topN, availableCount)}개를 표시하며, ${weightLabel}은 브라우저가 팩터 점수 비례 배분과 종목당 최대 ${formatPercent(maxWeight)} 가정으로 계산합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`,
  );
  const tbody = document.querySelector('#holdings-table tbody');
  tbody.replaceChildren();
  if (!weighted.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.textContent = '선택한 기준일과 팩터에 표시할 점수 스냅샷이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  weighted.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.display_rank);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.display_weight));
    appendCell(tr, factor);
    appendCell(tr, scoreDate || selectedDate());
    tbody.appendChild(tr);
  });
}

function renderCurrentOutputTable() {
  const run = currentRun();
  const topN = Math.max(1, Math.min(50, Number(document.querySelector('#topn-input').value || 20)));
  const rows = (run.latest_output_rows || []).slice(0, topN);
  const tbody = document.querySelector('#current-output-table tbody');
  tbody.replaceChildren();
  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.rank || index + 1);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, formatPercent(row.weight), { className: classForNumber(row.weight) });
    appendCell(tr, formatPercent(row.pre_cap_weight), { className: classForNumber(row.pre_cap_weight) });
    appendCell(tr, humanWeightingMethod(row.weighting_method));
    appendCell(tr, row.signal_date || run.summary?.data_as_of || '-');
    tbody.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 7;
    td.textContent = '최신 추천/연구 신호 출력 행이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

function renderFactorReturnChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const best = periodBestStats(run, date, windowKey);
  const matrix = periodMatrixEntry(run, date, windowKey);
  let rows = [];
  if (matrix && Array.isArray(matrix.factors)) {
    rows = matrix.factors.map((name, index) => ({
      factor: name,
      rank: index + 1,
      period_return: optionalNumber(matrix.returns?.[index]),
      window_label: matrix.window_label,
    }));
  } else {
    rows = (run.factor_period_rankings || []).filter((row) => row.date === date && row.window === windowKey);
  }
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 10);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText('#factor-chart-meta', `${date || '-'} · ${windowLabel} · 선택 ${factor || '-'}`);
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(
    target,
    `${row.rank}. ${row.factor}`,
    formatPercent(row.period_return),
    row.period_return,
    maxAbs,
    { className: `${row.factor === factor ? 'is-selected' : ''} ${row.factor === best?.factor ? 'is-best' : ''}`.trim() },
  ));
  if (!selectedRow) {
    const note = document.createElement('div');
    note.className = 'scenario-note';
    note.textContent = '선택 팩터가 이 기준일/기간의 내보낸 순위 데이터에 없습니다. 팩터 비교는 가능한 데이터 범위 안에서만 표시됩니다.';
    target.appendChild(note);
  }
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const selectedFactorName = selectedFactor();
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
    const factorNode = document.createElement('strong');
    factorNode.textContent = row.best_factor || '-';
    const detail = document.createElement('small');
    const selectedStats = periodFactorStats(run, row.date, row.window, selectedFactorName);
    detail.textContent = selectedStats?.rank
      ? `최고 수익률 ${formatPercent(row.best_return)} · 선택 팩터 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'}`
      : `최고 수익률 ${formatPercent(row.best_return)} · 선택 팩터 자료 없음`;
    chip.append(label, factorNode, detail);
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
  const run = currentRun();
  const { weighted, cashTotal, topN, maxWeight, unusedCandidateCount } = currentWeightedHoldings();
  const target = document.querySelector('#weight-chart');
  target.replaceChildren();
  setText('#weight-chart-meta', `${isPracticalRun(run) ? '투자 시나리오' : '연구 시나리오'} · 상위 ${topN}개 · 브라우저 최대 ${formatPercent(maxWeight)}`);
  if (!weighted.length) {
    appendEmpty('#weight-chart', '선택한 기준일과 팩터에 표시할 상위 종목 점수 스냅샷이 없습니다.');
    return;
  }
  const maxWeightValue = Math.max(
    ...weighted.map((row) => Number(row.display_weight) || 0),
    Number(cashTotal) || 0,
    0.01,
  );
  weighted.forEach((row) => appendBarRow(target, row.symbol, formatPercent(row.display_weight), row.display_weight, maxWeightValue));
  if (cashTotal > 0.000001) {
    appendBarRow(target, '현금/미사용', formatPercent(cashTotal), cashTotal, maxWeightValue);
  }
  if (unusedCandidateCount > 0) {
    const note = document.createElement('div');
    note.className = 'scenario-note';
    note.textContent = `상위 N개 제한 때문에 ${formatInteger(unusedCandidateCount)}개 후보는 이번 브라우저 시나리오 목표 비중에서 제외했습니다.`;
    target.appendChild(note);
  }
}

function factorBacktestSeries(run, factor) {
  return (run.factor_backtest_series || []).find((series) => series.factor === factor) || null;
}

function seriesPointsThroughDate(series, date, limit = 120) {
  if (!series || !Array.isArray(series.dates)) return [];
  const points = series.dates.map((pointDate, index) => ({
    date: pointDate,
    equity: Number(series.equity?.[index]),
    drawdown: Number(series.drawdown?.[index]),
  })).filter((point) => point.date && Number.isFinite(point.equity));
  const through = date ? points.filter((point) => String(point.date) <= String(date)) : points;
  return through.slice(-limit);
}

function normalizedLine(points) {
  if (!points.length) return [];
  const base = points[0].equity || 1;
  return points.map((point) => ({ ...point, normalized: base ? point.equity / base : point.equity }));
}

function renderBacktestChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const best = periodBestStats(run, date, windowKey);
  const selectedSeries = normalizedLine(seriesPointsThroughDate(factorBacktestSeries(run, factor), date));
  const bestSeries = best?.factor && best.factor !== factor
    ? normalizedLine(seriesPointsThroughDate(factorBacktestSeries(run, best.factor), date))
    : [];
  const target = document.querySelector('#backtest-chart');
  target.replaceChildren();
  setText('#backtest-chart-meta', `${date || '-'} 기준 · 선택 ${factor || '-'}${best?.factor ? ` · 기간 최고 ${best.factor}` : ''}`);
  if (!selectedSeries.length) {
    appendEmpty('#backtest-chart', '선택 팩터의 최근 백테스트 추이 데이터가 없습니다. 기간 최고 팩터 데이터를 대신 표시하지 않습니다.');
    return;
  }
  const allValues = [...selectedSeries, ...bestSeries].map((point) => point.normalized).filter((value) => Number.isFinite(value));
  const minValue = Math.min(...allValues, 0.95);
  const maxValue = Math.max(...allValues, 1.05);
  const width = 720;
  const height = 220;
  const pad = 18;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '선택 팩터와 기간 최고 팩터의 최근 백테스트 누적 성과 비교');
  [0.25, 0.5, 0.75].forEach((ratio) => {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    const y = pad + (height - pad * 2) * ratio;
    line.setAttribute('x1', String(pad));
    line.setAttribute('x2', String(width - pad));
    line.setAttribute('y1', String(y));
    line.setAttribute('y2', String(y));
    line.setAttribute('class', 'line-grid');
    svg.appendChild(line);
  });
  const toPolyline = (points) => points.map((point, index) => {
    const x = pad + (points.length <= 1 ? 0 : index / (points.length - 1) * (width - pad * 2));
    const y = height - pad - ((point.normalized - minValue) / Math.max(0.000001, maxValue - minValue)) * (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const appendLine = (points, className) => {
    if (!points.length) return;
    const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    polyline.setAttribute('points', toPolyline(points));
    polyline.setAttribute('class', `line-path ${className}`);
    svg.appendChild(polyline);
  };
  appendLine(selectedSeries, 'selected');
  appendLine(bestSeries, 'best');
  target.appendChild(svg);

  const legend = document.createElement('div');
  legend.className = 'line-legend';
  const selectedReturn = selectedSeries.at(-1)?.normalized - 1;
  const bestReturn = bestSeries.length ? bestSeries.at(-1)?.normalized - 1 : null;
  const selectedDrawdown = selectedSeries.at(-1)?.drawdown;
  const bestDrawdown = bestSeries.length ? bestSeries.at(-1)?.drawdown : null;
  const selectedLegend = document.createElement('span');
  const selectedDot = document.createElement('span');
  selectedDot.className = 'legend-dot';
  selectedLegend.appendChild(selectedDot);
  selectedLegend.append(`선택 팩터 ${factor}: 구간 ${formatPercent(selectedReturn)} · 낙폭 ${formatPercent(selectedDrawdown)}`);
  legend.appendChild(selectedLegend);
  if (bestSeries.length) {
    const bestLegend = document.createElement('span');
    const bestDot = document.createElement('span');
    bestDot.className = 'legend-dot best';
    bestLegend.appendChild(bestDot);
    bestLegend.append(`기간 최고 ${best.factor}: 구간 ${formatPercent(bestReturn)} · 낙폭 ${formatPercent(bestDrawdown)}`);
    legend.appendChild(bestLegend);
  }
  target.appendChild(legend);
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const matrix = periodMatrixEntry(run, date, windowKey);
  let rows = [];
  if (matrix && Array.isArray(matrix.factors)) {
    rows = matrix.factors.map((name, index) => ({
      window_label: matrix.window_label || windowKey,
      factor: name,
      period_return: optionalNumber(matrix.returns?.[index]),
      rank: index + 1,
    }));
  } else {
    rows = (run.factor_period_rankings || []).filter((row) => row.date === date && row.window === windowKey);
  }
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 40);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.window_label);
    appendCell(tr, row.factor, { strong: row.factor === factor });
    appendCell(tr, formatPercent(row.period_return), { className: classForNumber(row.period_return) });
    appendCell(tr, row.rank);
    tbody.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 4;
    td.textContent = '선택한 기준일과 기간에 팩터 랭킹 자료가 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

function renderAll() {
  renderSummary();
  renderDiagnostics();
  renderFactorReturnChart();
  renderBacktestChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
  renderCurrentOutputTable();
  renderFactorTable();
  renderHoldingsTable();
  renderPeriodRankingTable();
}

function renderWithBusy(message = '선택값을 반영하는 중입니다...') {
  setStatusMessage(message);
  window.setTimeout(() => {
    renderAll();
  }, 160);
}

bindManualUpdateControls();

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
      renderWithBusy('실행 결과를 전환하는 중입니다...');
    });
    document.querySelector('#factor-select').addEventListener('change', () => {
      fillDateOptions(currentRun(), selectedDate());
      renderWithBusy('선택 팩터를 반영하는 중입니다...');
    });
    ['#date-select', '#window-select', '#topn-input', '#max-weight-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => renderWithBusy('선택값을 반영하는 중입니다...'));
      document.querySelector(selector).addEventListener('change', () => renderWithBusy('선택값을 반영하는 중입니다...'));
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
    top_factor_count: int = 10,
    max_factor_rankings_per_period: int = MAX_FACTOR_RANKINGS_PER_PERIOD,
    max_score_snapshot_dates: int = MAX_SCORE_SNAPSHOT_DATES,
    max_score_snapshot_symbols: int = MAX_SCORE_SNAPSHOT_SYMBOLS,
    max_backtest_points: int = MAX_BACKTEST_POINTS,
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
    period_matrix = _factor_period_matrix_rows(
        factor_returns,
        max_history_days=max_history_days,
        max_factor_rankings_per_period=max_factor_rankings_per_period,
    )
    holding_rows = _holding_rows(
        result,
        leader_rows,
        max_holdings_per_period=max_holdings_per_period,
    )
    score_snapshots = _factor_score_snapshots(
        result,
        leader_rows,
        max_snapshot_dates=max_score_snapshot_dates,
        max_symbols=max_score_snapshot_symbols,
    )
    backtest_series = _factor_backtest_series(
        result,
        max_points=max_backtest_points,
    )
    latest_recommendations = result.recommendations.head(result.config.top_n).to_dict(orient="records")
    payload = _json_safe(
        {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "summary": summary,
            "periods": periods,
            "factor_options": _factor_options_payload(result),
            "factor_leaders": leader_rows,
            "factor_period_rankings": ranking_rows,
            "factor_period_matrix": period_matrix,
            "holdings": holding_rows,
            "factor_score_snapshots": score_snapshots,
            "scenario_available_dates": sorted(
                {row["date"] for row in score_snapshots if isinstance(row, dict) and row.get("date")},
                reverse=True,
            ),
            "scenario_available_dates_by_factor": _scenario_available_dates_by_factor(score_snapshots),
            "factor_backtest_series": backtest_series,
            "latest_output_rows": latest_recommendations,
            "data_quality_summary": _data_quality_summary(result),
            "tradability_gate": _tradability_gate_rows(result.metadata),
            "factor_diagnostics": _factor_diagnostics_payload(result),
            "notes_ko": [
                "웹사이트 입력값은 브라우저 표시용이며 다음 자동 실행 설정을 저장하지 않습니다.",
                "수동 업데이트 버튼은 공개 정적 페이지에 토큰을 저장하지 않고 GitHub Actions workflow_dispatch 화면으로 연결합니다.",
                "자동 실행 입력값은 .github/momentum-dashboard-config.json에서 관리합니다.",
                "모든 결과는 연구/의사결정 보조용이며 투자 조언이 아닙니다.",
            ],
        }
    )
    return _fit_dashboard_payload(payload, max_bytes=DASHBOARD_PAYLOAD_MAX_BYTES)


def write_dashboard_site(
    run_result_patterns: str | Path | Iterable[str | Path],
    site_dir: str | Path,
    *,
    title: str = DEFAULT_SITE_TITLE,
    history_limit: int = 60,
) -> dict[str, str]:
    """Write a static Korean dashboard site for one or more run-result JSON files."""

    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    paths = _expand_run_result_paths(run_result_patterns)
    if not paths:
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

    payloads = _merge_dashboard_history(
        data_path,
        [_payload_from_run_json(path) for path in paths],
        history_limit=history_limit,
    )
    combined = _json_safe(
        {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "title": title,
            "runs": payloads,
            "latest_run_index": len(payloads) - 1,
        }
    )
    combined = _fit_combined_dashboard_payload(combined, max_bytes=DASHBOARD_MAX_JSON_BYTES)

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
        "liquidity_eligible_universe_size": result.metadata.get("liquidity_eligible_universe_size"),
        "factor_count": result.metadata.get("factor_count"),
        "factor_library_scope": result.metadata.get("factor_library_scope"),
        "factor_rank_ic_horizon_days": result.metadata.get("factor_rank_ic_horizon_days"),
        "factor_high_redundancy_count": result.metadata.get("factor_high_redundancy_count"),
    }


GATE_LABELS_KO: dict[str, tuple[str, str]] = {
    "fresh_live_data": ("최신 실데이터", "전일/최근 미국 종가 데이터가 충분히 최신인지 확인합니다."),
    "factor_selection_policy_available": ("사전 정의된 팩터 선택 정책", "같은 실행에서 고른 팩터를 매매 권고로 쓰지 않도록 막습니다."),
    "no_explicit_price_symbol_cap": ("가격 수집 범위 제한 없음", "디버그용 종목 수 제한이 걸린 실행인지 확인합니다."),
    "complete_requested_price_coverage": ("요청 종목 가격 커버리지", "요청한 후보 종목이 가격/이력 조건을 충분히 통과했는지 확인합니다."),
    "broad_or_approved_tradable_universe": ("거래 가능 유니버스 근거", "충분히 넓거나 사용자가 승인한 거래 가능 후보군인지 확인합니다."),
    "point_in_time_universe": ("시점 기준 유니버스 근거", "생존편향을 줄이기 위한 시점 기준 유니버스 증거가 있는지 확인합니다."),
    "data_quality_manifest_available": ("데이터 품질 명세", "종목별 데이터 품질 진단표가 생성됐는지 확인합니다."),
    "row_level_data_quality_pass": ("추천 행 데이터 품질", "추천/신호 후보 행의 가격 품질이 기준을 통과했는지 확인합니다."),
    "liquidity_filter_evidence": ("유동성 근거", "거래량/거래대금 관측치가 충분한지 확인합니다."),
    "row_level_liquidity_pass": ("추천 행 유동성", "추천/신호 후보 행이 유동성 기준을 통과했는지 확인합니다."),
    "capacity_estimated_and_pass": ("운용 규모 수용성", "목표 운용규모와 ADV 참여율 기준에서 무리가 없는지 확인합니다."),
}


def _tradability_gate_rows(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = metadata.get("tradability_requirements", {})
    if not isinstance(requirements, dict):
        return []
    rows = []
    blockers = set(metadata.get("tradability_blockers") or metadata.get("fail_closed_reasons") or [])
    for key, passed in requirements.items():
        label, description = GATE_LABELS_KO.get(str(key), (str(key), "추가 실행 가능성 점검 항목입니다."))
        rows.append(
            {
                "key": str(key),
                "label_ko": label,
                "description_ko": description,
                "passed": bool(passed),
                "blocking": str(key) in blockers or not bool(passed),
            }
        )
    return rows


def _data_quality_summary(result: RunResult) -> dict[str, Any]:
    source_counts = {}
    if not result.data_sources.empty and "source" in result.data_sources:
        source_counts = result.data_sources["source"].value_counts().to_dict()
    status_counts = {}
    if not result.data_quality.empty and "data_quality_status" in result.data_quality:
        status_counts = result.data_quality["data_quality_status"].value_counts().to_dict()
    summary = result.metadata
    return {
        "candidate_universe_size": summary.get("candidate_universe_size"),
        "eligible_price_universe_size": summary.get("eligible_price_universe_size"),
        "liquidity_eligible_universe_size": summary.get("liquidity_eligible_universe_size"),
        "fetched_price_symbol_count": summary.get("fetched_price_symbol_count"),
        "excluded_symbols": summary.get("excluded_symbols"),
        "provider": summary.get("provider"),
        "data_as_of": summary.get("data_as_of"),
        "data_quality_status_counts": status_counts,
        "source_counts": source_counts,
        "liquidity_status_counts": summary.get("recommendation_liquidity_status_counts", {}),
        "capacity_status_counts": summary.get("recommendation_capacity_status_counts", {}),
    }


def _factor_diagnostics_payload(result: RunResult) -> dict[str, Any]:
    return {
        "scope_note_ko": (
            "현재 팩터 라이브러리는 가격 기반 모멘텀·추세·위험조정 변형입니다. 가치·퀄리티 같은 "
            "재무제표 팩터는 포함하지 않습니다. Forward Rank-IC는 연구용 탐색 진단이며 21거래일 "
            "미래수익률을 매일 중첩 관측하므로 관측 수를 독립 표본 수로 해석하면 안 됩니다."
        ),
        "rank_ic_horizon_days": result.metadata.get("factor_rank_ic_horizon_days"),
        "rank_ic_max_dates": result.metadata.get("factor_rank_ic_max_dates"),
        "diagnostic_methodology": result.metadata.get("factor_diagnostic_methodology", {}),
        "high_redundancy_count": result.metadata.get("factor_high_redundancy_count"),
        "category_summary": result.factor_category_summary.head(20).to_dict(orient="records"),
        "rank_ic_top": result.factor_rank_ic.head(10).to_dict(orient="records"),
        "redundancy_top": result.factor_redundancy.head(10).to_dict(orient="records"),
    }


FACTOR_CATEGORY_DESCRIPTIONS_KO: dict[str, str] = {
    "traditional": "장기 수익률에서 최근 과열 구간을 일부 제외해 지속성을 보려는 전통 모멘텀 계열입니다.",
    "recent": "최근 가격 상승 강도를 직접 비교하는 단기 상대강도 계열입니다.",
    "composite": "여러 기간의 가격 모멘텀을 합쳐 특정 기간 의존도를 줄이려는 복합 계열입니다.",
    "risk_adjusted": "수익률을 변동성이나 하방 위험으로 나누어 위험 대비 탄력을 보려는 계열입니다.",
    "trend": "이동평균과 추세 정렬로 상승 추세의 안정성을 보려는 계열입니다.",
    "drawdown": "고점 대비 낙폭이나 회복 정도로 추세 훼손 여부를 보려는 계열입니다.",
    "breakout": "최근 가격이 과거 범위를 돌파했는지 보는 추세 돌파 계열입니다.",
    "reversal": "단기 과열이나 되돌림 위험을 함께 고려하는 반전 보정 계열입니다.",
    "acceleration": "모멘텀의 변화 속도가 개선되는지 확인하는 가속도 계열입니다.",
    "quality": "추세의 일관성과 잡음 정도를 함께 보는 품질 계열입니다.",
    "cross_sectional": "동일 시점 후보군 안에서 상대 순위를 비교하는 횡단면 상대강도 계열입니다.",
    "robust": "극단값 영향을 줄여 과도한 한두 종목 효과를 완화하는 견고화 계열입니다.",
    "range": "최근 가격이 과거 거래 범위 안에서 어디에 위치하는지 보는 범위 위치 계열입니다.",
}


def _factor_options_payload(result: RunResult) -> list[dict[str, Any]]:
    definitions = result.factor_definitions.copy()
    if definitions.empty or "factor" not in definitions:
        definitions = pd.DataFrame({"factor": sorted(result.factor_scores)})
    score_components = result.score_components.copy()
    if not score_components.empty:
        score_components = score_components.reset_index(names="factor")
    rows = []
    for _, row in definitions.iterrows():
        factor = str(row.get("factor"))
        category = str(row.get("category", "unknown"))
        option: dict[str, Any] = {
            "factor": factor,
            "category": category,
            "description_ko": FACTOR_CATEGORY_DESCRIPTIONS_KO.get(
                category,
                "가격 흐름으로 상대 강도를 비교하는 모멘텀 팩터입니다.",
            ),
            "selected_by_run": factor == result.selected_factor,
        }
        if not score_components.empty and "factor" in score_components:
            match = score_components[score_components["factor"].eq(factor)]
            if not match.empty:
                for column in ["composite_score", "validation_sharpe", "validation_sortino", "validation_calmar"]:
                    if column in match:
                        option[column] = _float_or_none(match.iloc[0].get(column))
        rows.append(option)
    return sorted(rows, key=lambda item: (not item["selected_by_run"], item["factor"]))


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


def _factor_period_matrix_rows(
    period_returns: dict[str, pd.DataFrame],
    *,
    max_history_days: int,
    max_factor_rankings_per_period: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window_key, frame in period_returns.items():
        if frame.empty:
            continue
        for date, values in frame.dropna(how="all").tail(max_history_days).iterrows():
            clean = values.dropna().sort_values(ascending=False).head(max_factor_rankings_per_period)
            if clean.empty:
                continue
            rows.append(
                {
                    "date": _date_str(date),
                    "window": window_key,
                    "window_label": PERIOD_LABELS[window_key],
                    "factors": [str(factor) for factor in clean.index],
                    "returns": [_rounded_float(value) for value in clean.values],
                    "factor_count": int(values.dropna().size),
                    "exported_factor_count": int(clean.size),
                }
            )
    return rows


def _factor_score_snapshots(
    result: RunResult,
    leader_rows: list[dict[str, Any]],
    *,
    max_snapshot_dates: int,
    max_symbols: int,
) -> list[dict[str, Any]]:
    if not result.factor_scores or not leader_rows:
        return []
    dates = sorted({row["date"] for row in leader_rows if row.get("date")})[-max_snapshot_dates:]
    snapshots: list[dict[str, Any]] = []
    for date_text in dates:
        requested_date = pd.Timestamp(date_text)
        for factor in sorted(result.factor_scores):
            scores = result.factor_scores.get(factor)
            if scores is None or scores.empty:
                continue
            score_index = pd.DatetimeIndex(scores.index)
            score_date = _nearest_score_date(score_index, requested_date)
            if score_date is None:
                continue
            ranked = scores.loc[score_date].dropna().sort_values(ascending=False)
            if ranked.empty:
                continue
            top = ranked.head(max_symbols)
            snapshots.append(
                {
                    "date": date_text,
                    "factor": str(factor),
                    "score_date": _date_str(score_date),
                    "available_count": int(ranked.size),
                    "rows": [[str(symbol), _rounded_float(score)] for symbol, score in top.items()],
                }
            )
    return snapshots


def _factor_backtest_series(result: RunResult, *, max_points: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for factor in sorted(result.backtests):
        backtest = result.backtests[factor]
        equity = backtest.equity.dropna().sort_index()
        if equity.empty:
            continue
        drawdown = equity.divide(equity.cummax()).subtract(1.0)
        if len(equity) > max_points:
            equity = equity.tail(max_points)
            drawdown = drawdown.reindex(equity.index)
        rows.append(
            {
                "factor": str(factor),
                "dates": [_date_str(date) for date in equity.index],
                "equity": [_rounded_float(value) for value in equity.values],
                "drawdown": [_rounded_float(drawdown.loc[date]) for date in equity.index],
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
        backtest = result.backtests.get(factor)
        weight_frame = backtest.weights if backtest is not None else pd.DataFrame()
        weight_index = pd.DatetimeIndex(weight_frame.index) if not weight_frame.empty else pd.DatetimeIndex([])
        if scores is None or scores.empty or score_index is None or score_index.empty:
            continue
        requested_date = pd.Timestamp(leader["date"])
        weight_date = _nearest_score_date(weight_index, requested_date) if len(weight_index) else None
        weights = weight_frame.loc[weight_date] if weight_date is not None else pd.Series(dtype=float)
        active_weights = weights.dropna()
        active_weights = active_weights[active_weights.abs() > 1e-12].sort_values(ascending=False)
        if active_weights.empty:
            continue
        score_date = _active_signal_date(backtest, weight_date, score_index)
        if score_date is None:
            continue
        row_scores = scores.loc[score_date].dropna()
        active_symbols = [symbol for symbol in active_weights.index if symbol in row_scores.index]
        active_scores = row_scores.reindex(active_symbols).dropna().sort_values(ascending=False)
        if active_scores.empty:
            continue
        for rank, (symbol, score) in enumerate(active_scores.head(max_holdings_per_period).items(), start=1):
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
                    "default_weight": _float_or_none(active_weights.get(symbol, 0.0)),
                    "weight_date": _date_str(weight_date) if weight_date is not None else None,
                    "weight_source": "백테스트 일별 보유 비중",
                }
            )
    return rows


def _nearest_score_date(index: pd.DatetimeIndex, requested_date: pd.Timestamp) -> pd.Timestamp | None:
    positions = index.searchsorted(requested_date, side="right") - 1
    if positions < 0:
        return None
    return pd.Timestamp(index[int(positions)])


def _active_signal_date(backtest: Any, weight_date: pd.Timestamp | None, score_index: pd.DatetimeIndex) -> pd.Timestamp | None:
    if weight_date is None:
        return None
    signal_dates = getattr(backtest, "signal_dates", pd.Series(dtype="datetime64[ns]"))
    if isinstance(signal_dates, pd.Series) and not signal_dates.empty:
        rebalance_index = pd.DatetimeIndex(signal_dates.index)
        # Weights become effective on the trading day after a rebalance date, so
        # use the latest rebalance strictly before the displayed weight date.
        position = rebalance_index.searchsorted(weight_date, side="left") - 1
        if position >= 0:
            return pd.Timestamp(signal_dates.iloc[int(position)])
    return _nearest_score_date(score_index, weight_date)


def _payload_from_run_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("dashboard"), dict):
        dashboard = payload["dashboard"]
        dashboard.setdefault("source_json", str(path))
        dashboard.setdefault(
            "scenario_available_dates",
            sorted(
                {
                    row.get("date")
                    for row in dashboard.get("factor_score_snapshots", [])
                    if isinstance(row, dict) and row.get("date")
                },
                reverse=True,
            ),
        )
        dashboard.setdefault(
            "scenario_available_dates_by_factor",
            _scenario_available_dates_by_factor(
                [
                    row
                    for row in dashboard.get("factor_score_snapshots", [])
                    if isinstance(row, dict)
                ]
            ),
        )
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
            "factor_options": [
                {
                    "factor": selected_factor,
                    "category": "unknown",
                    "description_ko": "legacy JSON에서 읽은 선택 팩터입니다.",
                    "selected_by_run": True,
                }
            ] if selected_factor else [],
            "factor_leaders": factor_leaders,
            "factor_period_rankings": [],
            "factor_period_matrix": [
                {
                    "date": data_as_of,
                    "window": "latest",
                    "window_label": "최신",
                    "factors": [selected_factor] if selected_factor else [],
                    "returns": [None] if selected_factor else [],
                    "factor_count": 1 if selected_factor else 0,
                    "exported_factor_count": 1 if selected_factor else 0,
                }
            ] if selected_factor else [],
            "holdings": holdings,
            "factor_score_snapshots": [
                {
                    "date": data_as_of,
                    "factor": selected_factor,
                    "score_date": data_as_of,
                    "available_count": len(holdings),
                    "rows": [[row["symbol"], _rounded_float(row["score"])] for row in holdings if row.get("symbol")],
                }
            ] if selected_factor and holdings else [],
            "scenario_available_dates": [data_as_of] if selected_factor and holdings else [],
            "scenario_available_dates_by_factor": {selected_factor: [data_as_of]}
            if selected_factor and holdings
            else {},
            "factor_backtest_series": [],
            "latest_output_rows": rows[:50],
            "data_quality_summary": {
                "candidate_universe_size": metadata.get("candidate_universe_size"),
                "eligible_price_universe_size": metadata.get("eligible_price_universe_size"),
                "liquidity_eligible_universe_size": metadata.get("liquidity_eligible_universe_size"),
                "provider": metadata.get("provider"),
                "data_as_of": metadata.get("data_as_of"),
                "data_quality_status_counts": {},
                "source_counts": {},
            },
            "tradability_gate": _tradability_gate_rows(metadata),
            "factor_diagnostics": {
                "scope_note_ko": "legacy JSON에는 상세 팩터 진단이 없어 제한된 정보만 표시합니다.",
                "category_summary": payload.get("factor_category_summary", []) if isinstance(payload.get("factor_category_summary"), list) else [],
                "rank_ic_top": payload.get("factor_rank_ic", [])[:10] if isinstance(payload.get("factor_rank_ic"), list) else [],
                "redundancy_top": payload.get("factor_redundancy", [])[:10] if isinstance(payload.get("factor_redundancy"), list) else [],
            },
            "notes_ko": ["이 파일은 legacy run-results JSON에서 만든 제한적 대시보드 payload입니다."],
        }
    )


def _merge_dashboard_history(
    existing_data_path: Path,
    new_payloads: list[dict[str, Any]],
    *,
    history_limit: int,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if existing_data_path.exists():
        try:
            existing = json.loads(existing_data_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
            payloads.extend(item for item in existing["runs"] if isinstance(item, dict))
    payloads.extend(new_payloads)
    deduped: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        key = str(
            summary.get("run_timestamp_utc")
            or payload.get("source_json")
            or payload.get("generated_at_utc")
            or len(deduped)
        )
        deduped[key] = payload
    ordered = sorted(
        deduped.values(),
        key=lambda payload: str(
            (payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}).get("run_timestamp_utc")
            or payload.get("generated_at_utc")
            or ""
        ),
    )
    ordered = ordered[-history_limit:]
    if not ordered:
        return []
    compacted = [_compact_historical_run(payload) for payload in ordered[:-1]]
    latest = {**ordered[-1], "history_payload_type": "full"}
    return [*compacted, latest]


def _compact_historical_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep prior runs useful for comparison without shipping every holding row."""

    return _json_safe(
        {
            "schema_version": payload.get("schema_version", 1),
            "generated_at_utc": payload.get("generated_at_utc"),
            "source_json": payload.get("source_json"),
            "history_payload_type": "summary",
            "history_compaction_note_ko": (
                "이전 실행은 GitHub Pages 초기 로딩 속도를 위해 상위 보유 행과 최신 출력 행을 제거한 "
                "요약 이력입니다. 전체 종목/비중 상세는 최신 실행에서 확인하세요."
            ),
            "summary": payload.get("summary", {}),
            "periods": payload.get("periods", []),
            "factor_options": payload.get("factor_options", []),
            "factor_leaders": list(payload.get("factor_leaders", []))[-120:],
            "factor_period_rankings": list(payload.get("factor_period_rankings", []))[-120:],
            "factor_period_matrix": [],
            "holdings": [],
            "factor_score_snapshots": [],
            "scenario_available_dates": [],
            "scenario_available_dates_by_factor": {},
            "factor_backtest_series": [],
            "latest_output_rows": [],
            "data_quality_summary": payload.get("data_quality_summary", {}),
            "tradability_gate": payload.get("tradability_gate", []),
            "factor_diagnostics": payload.get("factor_diagnostics", {}),
            "notes_ko": [
                *(payload.get("notes_ko", []) if isinstance(payload.get("notes_ko"), list) else []),
                "과거 실행은 compact 요약으로 보관되어 상세 보유 비중 표시는 최신 실행에 한정됩니다.",
            ],
        }
    )


def _scenario_available_dates_by_factor(score_snapshots: list[dict[str, Any]]) -> dict[str, list[str]]:
    dates_by_factor: dict[str, set[str]] = {}
    for snapshot in score_snapshots:
        if not isinstance(snapshot, dict):
            continue
        factor = snapshot.get("factor")
        date = snapshot.get("date")
        if factor and date:
            dates_by_factor.setdefault(str(factor), set()).add(str(date))
    return {factor: sorted(dates, reverse=True) for factor, dates in sorted(dates_by_factor.items())}


def _json_payload_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))


def _fit_combined_dashboard_payload(payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    payload.setdefault("payload_limits", {})["max_json_bytes"] = max_bytes
    while _stamp_combined_payload_size(payload, max_bytes=max_bytes) > max_bytes and payload.get("runs"):
        latest_index = int(payload.get("latest_run_index", len(payload["runs"]) - 1))
        latest_index = max(0, min(latest_index, len(payload["runs"]) - 1))
        if _compact_combined_history_once(payload, latest_index=latest_index):
            continue
        latest = payload["runs"][latest_index]
        before = _json_payload_size(latest)
        payload["runs"][latest_index] = _fit_dashboard_payload(latest, max_bytes=max(500_000, before - 250_000))
        after = _json_payload_size(payload["runs"][latest_index])
        if after >= before:
            break
    while _stamp_combined_payload_size(payload, max_bytes=max_bytes) > max_bytes and payload.get("runs"):
        latest_index = int(payload.get("latest_run_index", len(payload["runs"]) - 1))
        latest_index = max(0, min(latest_index, len(payload["runs"]) - 1))
        if not _compact_combined_history_once(payload, latest_index=latest_index):
            break
    actual_size = _stamp_combined_payload_size(payload, max_bytes=max_bytes)
    if actual_size > max_bytes:
        raise ValueError(
            f"dashboard JSON exceeds hard size limit: "
            f"{actual_size} > {max_bytes} bytes"
        )
    return payload


def _stamp_combined_payload_size(payload: dict[str, Any], *, max_bytes: int) -> int:
    payload.setdefault("payload_limits", {})["max_json_bytes"] = max_bytes
    for _ in range(6):
        actual_size = _json_payload_size(payload)
        if payload["payload_limits"].get("actual_json_bytes") == actual_size:
            return actual_size
        payload["payload_limits"]["actual_json_bytes"] = actual_size
    return _json_payload_size(payload)


def _compact_combined_history_once(payload: dict[str, Any], *, latest_index: int) -> bool:
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    history_indexes = [index for index in range(len(runs)) if index != latest_index and isinstance(runs[index], dict)]
    for index in history_indexes:
        run = runs[index]
        before = _json_payload_size(run)
        if run.get("factor_period_matrix"):
            run["factor_period_matrix"] = []
        elif len(run.get("factor_period_rankings", [])) > 60:
            run["factor_period_rankings"] = list(run.get("factor_period_rankings", []))[-60:]
        elif run.get("factor_period_rankings"):
            run["factor_period_rankings"] = []
        elif len(run.get("factor_leaders", [])) > 40:
            run["factor_leaders"] = list(run.get("factor_leaders", []))[-40:]
        elif len(run.get("factor_options", [])) > 8:
            selected_factor = (run.get("summary", {}) if isinstance(run.get("summary"), dict) else {}).get(
                "selected_factor"
            )
            selected_options = [
                option for option in run.get("factor_options", []) if option.get("factor") == selected_factor
            ][:1]
            run["factor_options"] = [*selected_options, *list(run.get("factor_options", []))[:7]][:8]
        else:
            continue
        if _json_payload_size(run) < before:
            return True
    if len(runs) > 1:
        remove_index = 0 if latest_index != 0 else 1
        runs.pop(remove_index)
        payload["latest_run_index"] = len(runs) - 1
        return True
    return False


def _fit_dashboard_payload(payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    payload.setdefault("payload_limits", {})
    payload["payload_limits"].update(
        {
            "max_payload_bytes": max_bytes,
            "max_score_snapshot_symbols": MAX_SCORE_SNAPSHOT_SYMBOLS,
            "max_backtest_points": MAX_BACKTEST_POINTS,
            "snapshot_trim_policy": "가장 오래된 점수 스냅샷 날짜부터 줄입니다.",
        }
    )
    while _json_payload_size(payload) > max_bytes and payload.get("factor_score_snapshots"):
        dates = sorted({row.get("date") for row in payload["factor_score_snapshots"] if row.get("date")})
        if not dates:
            break
        oldest = dates[0]
        payload["factor_score_snapshots"] = [
            row for row in payload["factor_score_snapshots"] if row.get("date") != oldest
        ]
    while _json_payload_size(payload) > max_bytes and payload.get("factor_backtest_series"):
        changed = False
        for series in payload["factor_backtest_series"]:
            dates = series.get("dates") or []
            if len(dates) <= 80:
                continue
            indexes = list(range(len(dates)))[::2]
            if indexes[-1] != len(dates) - 1:
                indexes.append(len(dates) - 1)
            for key in ["dates", "equity", "drawdown"]:
                values = series.get(key) or []
                series[key] = [values[index] for index in indexes if index < len(values)]
            changed = True
        if not changed:
            break
    payload["scenario_available_dates"] = sorted(
        {row.get("date") for row in payload.get("factor_score_snapshots", []) if row.get("date")},
        reverse=True,
    )
    payload["scenario_available_dates_by_factor"] = _scenario_available_dates_by_factor(
        [row for row in payload.get("factor_score_snapshots", []) if isinstance(row, dict)]
    )
    payload["payload_limits"]["actual_payload_bytes"] = _json_payload_size(payload)
    payload["payload_limits"]["score_snapshot_dates_exported"] = len(payload["scenario_available_dates"])
    return payload


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


def _rounded_float(value: Any, digits: int = 6) -> float | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return round(number, digits)


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
