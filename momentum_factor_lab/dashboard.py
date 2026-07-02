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

from .data import build_eligibility_mask
from .universe import normalize_symbol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .workflow import RunResult


DASHBOARD_PERIODS: dict[str, int] = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}

DASHBOARD_MAX_JSON_BYTES = 5_000_000
DASHBOARD_PAYLOAD_MAX_BYTES = 3_800_000
MAX_FACTOR_RANKINGS_PER_PERIOD = 80
MAX_SCORE_SNAPSHOT_DATES = 24
MAX_SCORE_SNAPSHOT_SYMBOLS = 35
MIN_SCENARIO_SNAPSHOT_DATES = 1
MIN_SCENARIO_SNAPSHOT_SYMBOLS = 10
MAX_BACKTEST_POINTS = 220

PERIOD_LABELS: dict[str, str] = {
    "1M": "최근 1개월",
    "3M": "최근 3개월",
    "6M": "최근 6개월",
    "1Y": "최근 1년",
}

DEFAULT_SITE_TITLE = "모멘텀 팩터 데일리 대시보드"
ASSET_VERSION = "20260702-light-system-v6"


HTML_TEMPLATE = """<!doctype html>
<html lang="ko" data-project-id="momentum">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="assets/styles.css?v={asset_version}" />
  <link rel="stylesheet" href="assets/common-ui.css?v={asset_version}" />
  <script src="assets/common-ui.js?v={asset_version}" defer></script>
</head>
<body id="top">
  <header class="hero">
    <nav class="top-nav" data-common-nav aria-label="Quant 프로젝트 공통 이동"></nav>
    <div>
      <p class="eyebrow">모멘텀 팩터 랩</p>
      <h1>{title}</h1>
      <p class="hero-copy">
        미국 종가 기준 모멘텀 팩터를 매일 비교합니다.
        핵심 팩터, 상위 종목, 표시용 비중을 먼저 보고 필요한 표로 내려갑니다.
      </p>
      <div class="hero-actions">
        <a class="button hero-link" href="https://sonchanggi.github.io/quant-dashboard/" aria-label="투자 리서치 프로젝트 통합 대시보드로 돌아가기">← 통합 대시보드로 돌아가기</a>
      </div>
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


    <section class="controls controls-enhanced" aria-label="대시보드 입력값">
      <div class="control-group control-group-run">
        <div class="control-group-heading">
          <p class="eyebrow">분석 기준</p>
          <h2>기준일 · 기간 · 선택 팩터</h2>
        </div>
        <label>실행 결과
          <select id="run-select"></select>
        </label>
        <label>기준일
          <select id="date-select"></select>
        </label>
        <label>최근 기간
          <select id="window-select"></select>
          <span class="control-hint">기본값은 최근 12개월입니다.</span>
        </label>
        <label>선택 팩터 시나리오
          <select id="factor-select"></select>
          <span class="control-hint">초기값은 현재 기준일·기간의 최고 팩터입니다.</span>
        </label>
      </div>
      <div class="control-group control-group-backtest">
        <div class="control-group-heading">
          <p class="eyebrow">백테스트 민감도 조건</p>
          <h2>브라우저 프록시 시나리오 입력</h2>
          <p class="control-hint">저장된 팩터 백테스트 곡선을 현재 입력값으로 조정한 민감도 뷰입니다. 새 백엔드 재백테스트나 저장된 매매 조건은 아닙니다.</p>
        </div>
        <label>최근 분석 기간
          <select id="lookback-months-select">
            <option value="3">최근 3개월</option>
            <option value="6">최근 6개월</option>
            <option value="12" selected>최근 12개월</option>
            <option value="24">최근 24개월</option>
          </select>
        </label>
        <label>상위 N개 종목
          <input id="topn-input" type="number" min="1" max="50" value="20" />
          <span class="control-hint">기본값 20개. 점수 스냅샷 범위 내에서 계산합니다.</span>
        </label>
        <label>브라우저 시나리오 종목당 최대 비중
          <input id="max-weight-input" type="number" min="1" max="50" step="1" value="50" />
          <span class="unit">%</span>
          <span class="control-hint">표시용 가정 기본값 50%. 변경 시 비중·백테스트 시나리오가 함께 갱신됩니다.</span>
        </label>
        <label>리밸런싱 주기
          <select id="rebalance-select">
            <option value="W">주간</option>
            <option value="ME" selected>월간</option>
            <option value="QE">분기</option>
          </select>
        </label>
        <label>거래 비용
          <input id="transaction-cost-input" type="number" min="0" max="200" step="1" value="5" />
          <span class="unit">bps</span>
        </label>
        <label>슬리피지
          <input id="slippage-input" type="number" min="0" max="200" step="1" value="5" />
          <span class="unit">bps</span>
        </label>
        <div class="preset-row" aria-label="빠른 입력 프리셋">
          <button type="button" data-topn-preset="10">상위 10</button>
          <button type="button" data-topn-preset="20">상위 20</button>
          <button type="button" data-topn-preset="30">상위 30</button>
          <button type="button" data-max-weight-preset="10">최대 10%</button>
          <button type="button" data-max-weight-preset="20">최대 20%</button>
          <button type="button" data-max-weight-preset="50">최대 50%</button>
        </div>
        <p id="scenario-live-summary" class="scenario-live-summary" aria-live="polite">선택값을 불러오는 중입니다.</p>
      </div>
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
      <article class="diagnostic-card factor-method-card">
        <div class="method-card-heading">
          <div>
            <p class="eyebrow">선택 팩터 계산법</p>
            <h3 id="selected-factor-method-title">-</h3>
          </div>
          <span id="selected-factor-method-badge" class="badge">브라우저 시나리오 설명</span>
        </div>
        <p id="selected-factor-method-summary" class="method-summary">선택한 팩터의 산식과 현재 입력값 적용 방식을 표시합니다.</p>
        <div id="selected-factor-method-steps" class="method-grid" aria-live="polite"></div>
        <p id="selected-factor-method-note" class="scenario-note">팩터 설명을 불러오는 중입니다.</p>
        <p class="scenario-note method-glossary"><strong>용어:</strong> 여기서 원자료는 원화(KRW)가 아니라 서버가 저장한 기존 백테스트/산출 원본값입니다. “시나리오”는 화면 입력값(상위 N, 최대 비중, 리밸런싱, 비용)을 적용해 원자료를 다시 해석한 브라우저 민감도 표시입니다.</p>
      </article>
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
          선택 팩터 시나리오, 기간 최고 팩터, 상위 팩터 묶음 효과를 분리해 빠르게 파악하도록 구성했습니다.
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
          <div id="performance-metrics-table" class="performance-metrics" aria-live="polite"></div>
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
        <article class="viz-card">
          <div class="viz-card-heading">
            <div>
              <p class="eyebrow">팩터 앙상블</p>
              <h3>상위 10개 팩터 동일비중 합산</h3>
            </div>
            <span id="ensemble-chart-meta" class="chart-meta">-</span>
          </div>
          <div id="ensemble-weight-chart" class="bar-chart compact-bars" aria-live="polite"></div>
        </article>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">최신 출력</p>
          <h2>기존 결과물 기준 · 해당 날짜 최고 팩터 추천/연구 신호</h2>
        </div>
        <p>
          기준일·기간 최고 팩터의 기존 출력입니다. 매매 비중 0%는 연구용 신호이며 주문 비중이 아닙니다.
          게이트 전 모형 비중은 후보 간 상대 강도 진단값이고, 선택 팩터 시나리오는 아래 별도 영역에서 비교합니다.
        </p>
      </div>
      <p id="current-output-note" class="scenario-note">-</p>
      <div class="table-wrap">
        <table id="current-output-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>종목</th>
              <th>모멘텀 신호</th>
              <th>기준 팩터</th>
              <th>최종 매매 비중</th>
              <th>게이트 전 모형 비중</th>
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
              <th>브라우저 시나리오 최고 수익률</th>
              <th>선택 팩터 시나리오 수익률</th>
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

    <section class="panel analysis-panel" id="daily-weight-analysis-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">추가 분석</p>
          <h2>선택 팩터 일별 투자 비중</h2>
        </div>
        <p id="daily-weight-analysis-note">선택한 기준일·팩터의 백테스트 일별 보유 비중과 브라우저 입력값으로 재계산한 시나리오 비중을 함께 확인합니다.</p>
      </div>
      <div class="table-wrap">
        <table id="daily-weights-table">
          <thead>
            <tr>
              <th>비중일</th>
              <th>기간</th>
              <th>종목별 저장/시나리오 비중</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <details class="panel two-col">
      <summary>대시보드 설명</summary>
      <div class="details-body">
      <div>
        <p class="eyebrow">최신 팩터 랭킹</p>
        <h2>기준일별 기간 수익률 상위 팩터</h2>
        <div class="table-wrap compact">
          <table id="period-ranking-table">
                <thead><tr><th>기간</th><th>팩터</th><th>시나리오/원자료 수익률</th><th>순위</th></tr></thead>
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
          </div>
    </details>

    <details class="manual-update" aria-label="수동 최신 데이터 업데이트">
      <summary>수동 업데이트</summary>
      <div class="details-body">
      <div>
        <p class="eyebrow">수동 업데이트</p>
        <h2>검토 후 그 시점의 최신 데이터로 수동 실행</h2>
        <p>
          자동 예약 실행은 현재 중지되어 있습니다. 검토 후 이 버튼으로 GitHub Actions
          <code>workflow_dispatch</code> 파이프라인을 수동 실행할 수 있습니다.
          저장소 쓰기 권한이 있는 GitHub 계정으로 로그인한 뒤 <strong>Run workflow</strong>를 누르면
          실행 시점에 무료 제공자가 제공하는 가장 최근 미국 일별 종가까지 다시 수집하고, 팩터 백테스트,
          종목/비중 산출, <code>docs/data/dashboard.json</code> 갱신, GitHub Pages 배포를 진행합니다.
        </p>
        <p class="manual-update-note">
          보안상 공개 정적 페이지에는 GitHub 토큰을 저장하지 않습니다. 브라우저 버튼은 인증된
          GitHub 수동 실행 화면으로 연결하며, provider가 아직 새 종가를 공개하지 않았거나 변경사항이 없으면
          새 커밋 없이 종료될 수 있습니다. 실행 후 Actions 상태와 대시보드 기준일·최근 실행 시각을 확인하세요.
        </p>
      </div>
      <div class="manual-update-actions">
        <a id="manual-update-button" class="button primary" href="https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml" target="_blank" rel="noopener">GitHub Actions에서 최신 데이터 업데이트 실행</a>
        <button id="copy-update-command" class="button secondary" type="button">CLI 실행 명령 복사</button>
        <code id="manual-update-command" class="code-pill">gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main</code>
        <small id="manual-update-status" role="status" aria-live="polite">실행 후 변경사항이 있으면 새 JSON이 커밋되고 Pages가 갱신됩니다. Actions 상태와 대시보드 기준일을 확인하세요.</small>
      </div>
          </div>
    </details>

    <details class="notice moved-notice">
      <summary>운영 고지</summary>
      <div class="details-body">
      <strong>운영 고지:</strong> 이 웹사이트의 선택값은 브라우저에서 비교/표시만 바꾸며,
      다음 수동 실행 입력값을 저장하지 않습니다. 검토된 live-run 입력값은 저장소의
      <code>.github/momentum-dashboard-config.json</code>에서 관리됩니다.
      2026-06-20 데이터 축소 롤백 이후 자동 예약 실행과 watchdog 예약은 중지되어 있으며,
      새 데이터 반영은 <code>workflow_dispatch</code> 수동 실행 후 publication safety gate를 통과해야 합니다.
          </div>
    </details>

    <details class="disclaimer">
      <summary>주의 및 한계</summary>
      <div class="details-body">
      <h2>주의 및 한계</h2>
      <p>
        본 대시보드는 연구/의사결정 보조용이며 개인화된 투자, 세무, 법률 또는 매매 조언이 아닙니다.
        무료/공개 데이터의 누락, 조정가격 차이, 생존편향, 유동성/용량 한계가 있을 수 있습니다.
      </p>
          </div>
    </details>
  </main>

  <footer>
    <span>모멘텀 팩터 랩에서 생성</span>
    <span id="generated-at"></span>
  </footer>
  <script src="assets/dashboard.js?v=20260701-ralph-table-v5d"></script>
  <nav class="page-jump-nav" aria-label="페이지 빠른 이동">
    <a href="#top" aria-label="맨 위로 이동">↑ 위</a>
    <a href="#page-bottom" aria-label="맨 아래로 이동">↓ 아래</a>
  </nav>
  <div id="page-bottom" tabindex="-1" aria-hidden="true"></div>
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
html, body { max-width: 100%; overflow-x: hidden; }
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
.hero-actions { margin-top: 1.25rem; display: flex; flex-wrap: wrap; gap: .75rem; }
.hero-link { color: #0f2f68; background: rgba(255,255,255,.92); border-color: rgba(255,255,255,.55); box-shadow: 0 14px 30px rgba(15, 23, 42, .18); }
.hero-link:hover { background: #fff; transform: translateY(-1px); }
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
.panel, .controls > *, .cards > *, .two-col > *, .viz-grid > *, .diagnostic-grid > *, .manual-update > * { min-width: 0; }
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
  min-width: 0; max-width: 100%;
  border: 1px solid var(--line); border-radius: 22px; padding: 1rem;
  background: rgba(255,255,255,.86); box-shadow: 0 10px 24px rgba(15, 23, 42, .05);
}
.viz-card.wide { grid-column: 1 / -1; }
.viz-card-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; margin-bottom: .9rem; min-width: 0; }
.viz-card h3 { margin: 0; font-size: 1.05rem; }
.chart-meta { color: var(--muted); font-size: .82rem; font-weight: 800; text-align: right; line-height: 1.4; overflow-wrap: anywhere; min-width: 0; }
.bar-chart { display: grid; gap: .62rem; min-width: 0; }
.bar-row { display: grid; grid-template-columns: minmax(0, .9fr) minmax(140px, 2fr) 88px; gap: .75rem; align-items: center; min-width: 0; }
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
.line-chart { min-height: 260px; max-width: 100%; min-width: 0; border: 1px solid var(--line); border-radius: 18px; background: #fff; padding: .85rem; }
.line-chart svg { display: block; width: 100%; height: 260px; overflow: visible; }
.line-grid { stroke: #e2e8f0; stroke-width: 1; }
.axis-line { stroke: #94a3b8; stroke-width: 1.2; }
.axis-label { fill: #64748b; font-size: 10px; font-weight: 700; }
.axis-title { fill: #475569; font-size: 11px; font-weight: 900; }
.line-path { fill: none; stroke-width: 2.8; stroke-linecap: round; stroke-linejoin: round; }
.line-path.selected { stroke: var(--accent); }
.line-path.best { stroke: var(--good); stroke-dasharray: 5 5; }
.line-path.benchmark { stroke: #7c3aed; stroke-dasharray: 2 4; }
.line-legend { display: flex; flex-wrap: wrap; gap: .7rem; margin-top: .75rem; color: #334155; font-size: .84rem; line-height: 1.45; }
.legend-dot { display: inline-block; width: .7rem; height: .7rem; border-radius: 50%; margin-right: .35rem; vertical-align: -.05rem; background: var(--accent); }
.legend-dot.best { background: var(--good); }
.legend-dot.benchmark { background: #7c3aed; }
.performance-metrics { margin-top: 1rem; display: grid; gap: .7rem; }
.performance-metrics-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: end; flex-wrap: wrap; }
.performance-metrics-heading h4 { margin: 0; font-size: 1rem; }
.performance-metrics-heading p { margin: .25rem 0 0; color: var(--muted); font-size: .86rem; line-height: 1.55; }
.factor-method-card { margin: 1rem 0; }
.method-card-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; flex-wrap: wrap; }
.method-card-heading h3 { margin: .15rem 0 0; font-size: 1.15rem; overflow-wrap: anywhere; }
.method-summary { margin: .8rem 0; color: var(--muted); line-height: 1.65; }
.method-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
.method-item { border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.04); padding: .8rem; min-width: 0; }
.method-item strong { display: block; margin-bottom: .3rem; color: var(--ink); font-size: .86rem; }
.method-item small { color: var(--muted); line-height: 1.5; }
.performance-period-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .85rem; align-items: start; }
.performance-period-card { border: 1px solid var(--line); border-radius: 18px; background: #fff; overflow: hidden; box-shadow: 0 10px 24px rgba(15, 23, 42, .04); }
.performance-period-card h5 { margin: 0; padding: .8rem .95rem; font-size: .95rem; background: #f8fafc; border-bottom: 1px solid var(--line); }
.performance-table-wrap { overflow-x: auto; }
.performance-table { width: 100%; min-width: 0; table-layout: fixed; }
.performance-table th, .performance-table td { padding: .58rem .7rem; vertical-align: middle; }
.performance-table th:first-child, .performance-table td:first-child { width: 34%; min-width: 0; white-space: normal; }
.performance-table th:not(:first-child), .performance-table td:not(:first-child) { width: 22%; text-align: right; white-space: nowrap; }
.metric-name { font-weight: 900; color: #0f172a; }
.series-name { color: var(--muted); display: inline-block; font-size: .78rem; font-weight: 800; line-height: 1.2; white-space: normal; }
.series-name.selected { color: var(--accent); }
.series-name.best { color: var(--good); }
.series-name.benchmark { color: #7c3aed; }
@media (max-width: 1180px) {
  .performance-period-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .performance-period-grid { grid-template-columns: 1fr; }
  .performance-table th, .performance-table td { padding: .52rem .55rem; }
  .method-grid { grid-template-columns: 1fr; }
}
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

/* Visual Ralph dark-neutral luxury refresh — design-only, 2026-06-24.
   Preserve analysis logic, JSON/data contracts, and result semantics. */
:root {
  color-scheme: dark;
  --bg: #080a0f;
  --panel: rgba(18, 22, 30, 0.94);
  --card: rgba(18, 22, 30, 0.94);
  --surface: rgba(18, 22, 30, 0.94);
  --surface-soft: rgba(31, 36, 48, 0.86);
  --ink: #f4f4f5;
  --muted: #9aa4b2;
  --line: rgba(226, 232, 240, 0.14);
  --accent: #7dd3fc;
  --accent-2: #c4b5fd;
  --accent-soft: rgba(125, 211, 252, 0.12);
  --primary: #d8dee8;
  --primary-dark: #f4f4f5;
  --good: #86efac;
  --success: #86efac;
  --warn: #fbbf24;
  --warning: #fbbf24;
  --danger: #fb7185;
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
}

html { background: #080a0f; }

body {
  color: var(--ink) !important;
  background:
    radial-gradient(circle at 12% -4%, rgba(216, 222, 232, 0.13), transparent 32rem),
    radial-gradient(circle at 82% 8%, rgba(125, 211, 252, 0.08), transparent 30rem),
    linear-gradient(180deg, #0d1016 0%, #080a0f 46%, #090b10 100%) !important;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
  background-size: 72px 72px;
  mask-image: linear-gradient(180deg, rgba(0,0,0,.8), transparent 82%);
}

a { color: inherit; }
a:hover { color: #f4f4f5; }
code {
  color: #d8dee8 !important;
  background: rgba(216, 222, 232, 0.09) !important;
  border: 1px solid rgba(216, 222, 232, 0.12);
}

.eyebrow,
.hero .eyebrow {
  color: #d8dee8 !important;
  letter-spacing: .12em;
}

.hero,
.hero-main {
  color: #f4f4f5 !important;
  background:
    radial-gradient(circle at 78% 0%, rgba(125, 211, 252, 0.12), transparent 28rem),
    linear-gradient(135deg, rgba(23, 28, 38, 0.96) 0%, rgba(12, 15, 21, 0.98) 100%) !important;
  border-color: rgba(226, 232, 240, 0.14) !important;
}

.hero::after,
.hero-main::after {
  background: rgba(216, 222, 232, 0.05) !important;
}

.hero-copy,
.hero-main .hero-copy,
.section-heading p,
.panel-heading p,
.notice,
.disclaimer,
.explain,
.hero-note p,
.site-footer,
.helper,
.manual-update p,
.analysis-card p,
.diagnostic-note,
.control-hint,
.chart-meta,
.chart-help,
.axis-note,
.scale-legend,
.scale-foot,
.card small,
.project-card p,
.metric-card small,
.status-value,
.lookup-status,
.company-summary p,
.methodology-section p {
  color: var(--muted) !important;
}

.top-nav {
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(12, 15, 21, 0.74);
  box-shadow: 0 10px 36px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(18px);
}

.top-nav a,
.panel-link,
.hero-actions a,
.project-card a,
.hero-link,
.primary-button,
.secondary-button,
.button,
button,
.text-button,
.ticker-form button,
.ticker-filters button,
.sample-tickers button,
.control-card button,
.hero-dashboard-button {
  color: #f4f4f5 !important;
  background: rgba(244, 244, 245, 0.075) !important;
  border-color: rgba(226, 232, 240, 0.18) !important;
  box-shadow: none !important;
}

.hero-actions a:first-child,
.hero-main .primary-button,
.button.primary,
button.primary,
.ticker-form button[type="submit"] {
  color: #0a0d12 !important;
  background: linear-gradient(135deg, #f4f4f5, #b9c0cb) !important;
  border-color: transparent !important;
}

.top-nav a:hover,
.panel-link:hover,
.hero-actions a:hover,
.project-card a:hover,
.button:hover,
button:hover,
.text-button:hover,
.hero-dashboard-button:hover {
  transform: translateY(-1px);
  border-color: rgba(244, 244, 245, 0.36) !important;
  background: rgba(244, 244, 245, 0.12) !important;
}

.hero-grid > div,
.hero-note,
.panel,
.project-card,
.metric-card,
.chart-card,
.notice-card,
.lookup-status,
.company-section,
.methodology-section,
.control-card,
.manual-update,
.feature-grid article,
.signal-card,
.notice,
.disclaimer,
.controls,
.card,
.viz-card,
.diagnostic-card,
.analysis-card,
.metric-tile,
.command-card,
.status-card,
.update-panel,
.economic-panel,
.visual-panel,
.forecast-chart,
.valuation-band,
.valuation-scale,
.assumption-form,
.radar-grid,
.company-card,
.summary-card,
.state-card {
  color: var(--ink) !important;
  background: linear-gradient(180deg, rgba(23, 28, 38, 0.94), rgba(14, 17, 23, 0.96)) !important;
  border-color: var(--line) !important;
  box-shadow: var(--shadow) !important;
}

.hero-grid > div,
.hero-note,
.panel,
.project-card,
.metric-card,
.chart-card,
.notice-card,
.lookup-status,
.company-section,
.methodology-section,
.control-card,
.manual-update,
.feature-grid article,
.signal-card,
.notice,
.disclaimer,
.controls,
.card,
.viz-card,
.diagnostic-card,
.analysis-card,
.metric-tile,
.command-card,
.status-card,
.update-panel,
.economic-panel,
.visual-panel,
.forecast-chart,
.valuation-band,
.valuation-scale,
.assumption-form,
.radar-grid {
  position: relative;
}

.hero-grid > div::after,
.hero-note::after,
.panel::after,
.project-card::after,
.metric-card::after,
.chart-card::after,
.card::after,
.status-card::after {
  content: "";
  position: absolute;
  inset: 1px;
  border-radius: inherit;
  pointer-events: none;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.07);
}

h1, h2, h3,
.panel-heading h2,
.metric-card strong,
.card strong,
.project-card h3,
.status-card strong,
.metric-tile-header strong,
.analysis-card h3,
.diagnostic-card h3,
.forecast-chart h3 {
  color: var(--ink) !important;
}

.metric-card,
.metric-tile,
.project-card,
.card,
.diagnostic-card,
.analysis-card,
.chart-summary-item,
.state,
.gate-item,
.mini-item,
.schedule-list li,
.command-card,
.value-card {
  background: rgba(255, 255, 255, 0.035) !important;
  border-color: rgba(226, 232, 240, 0.11) !important;
}

select,
input,
textarea {
  color: #f4f4f5 !important;
  background: rgba(8, 10, 15, 0.72) !important;
  border-color: rgba(226, 232, 240, 0.18) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}

select:focus-visible,
input:focus-visible,
textarea:focus-visible,
a:focus-visible,
button:focus-visible,
[tabindex]:focus-visible {
  outline: 3px solid rgba(125, 211, 252, 0.55) !important;
  outline-offset: 3px;
}

input[readonly],
input:disabled,
select:disabled,
button:disabled {
  color: #8e96a3 !important;
  background: rgba(255, 255, 255, 0.04) !important;
  border-color: rgba(226, 232, 240, 0.10) !important;
}

.table-wrap,
.table-scroll,
.data-table-wrap {
  border-color: var(--line) !important;
  background: rgba(8, 10, 15, 0.44) !important;
}

table,
thead,
tbody {
  color: #d8dee8 !important;
  background: rgba(8, 10, 15, 0.32) !important;
}

th,
td {
  color: #d8dee8 !important;
  border-bottom-color: rgba(226, 232, 240, 0.10) !important;
}

th {
  color: #aab3c2 !important;
  background: rgba(255, 255, 255, 0.055) !important;
}

tbody tr:nth-child(even),
tbody tr:hover {
  background: rgba(125, 211, 252, 0.055) !important;
}

.badge,
.status-pill,
.selected-chip,
.chip,
.card-badge,
.tag,
.pill {
  color: #d8dee8 !important;
  background: rgba(216, 222, 232, 0.09) !important;
  border: 1px solid rgba(216, 222, 232, 0.16) !important;
}

.badge.good,
.status-pill.success,
.status-pill.secondary,
.gate-item.pass,
.positive {
  color: var(--good) !important;
}

.badge.warn,
.status-pill.warning,
.gate-item.block,
.valuation-scale.neutral .scale-fill {
  color: var(--warning) !important;
}

.badge.error,
.status-pill.danger,
.status-card.error,
.negative {
  color: var(--danger) !important;
}

.line-chart,
.chart,
.chart-card,
.forecast-chart {
  background:
    linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px) 0 0 / 100% 25%,
    linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px) 0 0 / 12.5% 100%,
    rgba(4, 6, 10, 0.28) !important;
  border-color: rgba(226, 232, 240, 0.12) !important;
}

svg text,
.chart-card svg text,
.line-chart svg text,
.chart svg text {
  fill: #aab3c2 !important;
}

svg line,
.axis-line,
.axis,
.chart-card .axis-row line,
.chart-card .axis-column line,
.line-chart .axis-line {
  stroke: rgba(226, 232, 240, 0.20) !important;
}

.axis-label,
.axis-title,
.chart-card .axis-row text,
.chart-card .axis-column text,
.chart-card .axis-title,
.chart-card .axis-range,
.line-end-label text {
  fill: #aab3c2 !important;
  color: #aab3c2 !important;
}

.bar-track,
.scale-track {
  background: rgba(226, 232, 240, 0.12) !important;
  border: 1px solid rgba(226, 232, 240, 0.09);
}

.bar-fill,
.trend-fill,
.scale-fill,
.forecast-bar.fcf {
  background: linear-gradient(90deg, #7dd3fc, #c4b5fd) !important;
}

.bar-fill.negative,
.trend-fill.negative,
.valuation-scale.negative .scale-fill {
  background: linear-gradient(90deg, #fb7185, #fca5a5) !important;
}

.valuation-scale.positive .scale-fill,
.forecast-bar.pv {
  background: linear-gradient(90deg, #86efac, #7dd3fc) !important;
}

.sensitivity-cell.positive,
.value-cell.positive {
  background: rgba(134, 239, 172, 0.10) !important;
}
.sensitivity-cell.negative,
.value-cell.negative {
  background: rgba(251, 113, 133, 0.10) !important;
}
.sensitivity-cell.neutral,
.value-cell.neutral {
  background: rgba(251, 191, 36, 0.10) !important;
}

.legend,
.line-legend,
.chart-legend {
  color: #aab3c2 !important;
}

.comparison-line.best { stroke: #7dd3fc !important; }
.comparison-line.selected { stroke: #fbbf24 !important; }
.comparison-line.benchmark { stroke: #86efac !important; }
.legend-dot.best { background: #7dd3fc !important; }
.legend-dot.selected { background: #fbbf24 !important; }
.legend-dot.benchmark { background: #86efac !important; }
.series-name.selected { color: #fbbf24 !important; }
.series-name.best { color: #7dd3fc !important; }
.series-name.benchmark { color: #86efac !important; }

.noscript-warning,
.notice.warning {
  color: #fee9a8 !important;
  background: rgba(251, 191, 36, 0.11) !important;
  border-color: rgba(251, 191, 36, 0.28) !important;
}

::-webkit-scrollbar { width: 12px; height: 12px; }
::-webkit-scrollbar-track { background: #080a0f; }
::-webkit-scrollbar-thumb { background: rgba(216, 222, 232, 0.22); border-radius: 999px; border: 3px solid #080a0f; }
::-webkit-scrollbar-thumb:hover { background: rgba(216, 222, 232, 0.34); }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}

/* Visual Ralph iteration-2 premium spacing refinement. */
.hero {
  width: min(1320px, calc(100% - 48px));
  margin: 28px auto 0;
  border: 1px solid rgba(226, 232, 240, 0.14) !important;
  border-radius: 30px;
  box-shadow: 0 28px 90px rgba(0,0,0,.38);
}

.hero h1 {
  letter-spacing: -0.065em;
  line-height: .98;
}

main {
  width: min(1320px, calc(100% - 48px));
  margin-inline: auto;
  padding-left: 0 !important;
  padding-right: 0 !important;
}

.section,
.site-footer {
  width: min(1320px, calc(100% - 48px)) !important;
}

.notice,
.manual-update,
.controls,
.cards,
.panel,
.dashboard-grid,
.metric-row,
.project-grid,
.feature-grid,
.company-section,
.methodology-section,
.lookup-status,
.notice-section,
.dashboard-section {
  margin-bottom: 24px !important;
}

.controls,
.control-card,
.manual-update,
.notice,
.panel,
.card,
.metric-card,
.project-card,
.hero-note,
.status-card,
.notice-card,
.lookup-status,
.company-section,
.methodology-section,
.feature-grid article,
.signal-card {
  border-radius: 24px !important;
}

.panel,
.manual-update,
.controls,
.control-card,
.notice-card,
.lookup-status,
.company-section,
.methodology-section {
  padding: clamp(22px, 2.4vw, 34px) !important;
}

.cards,
.metric-row,
.project-grid,
.feature-grid,
.dashboard-grid,
.analysis-grid,
.diagnostic-grid,
.viz-grid,
.two-col,
.update-grid {
  gap: 18px !important;
}

.card,
.metric-card,
.project-card,
.diagnostic-card,
.analysis-card,
.metric-tile,
.chart-summary-item {
  padding: 20px !important;
  min-height: 142px;
}

.card strong,
.metric-card strong,
.project-card h3 {
  font-size: clamp(1.2rem, 2vw, 1.65rem) !important;
}

.panel-heading {
  margin-bottom: 20px !important;
}

.panel-heading h2,
.section-heading h2,
.manual-update h2 {
  font-size: clamp(1.7rem, 3.1vw, 2.85rem) !important;
}

.line-chart,
.chart-card,
.chart,
.forecast-chart {
  border-radius: 22px !important;
}

.top-nav,
.hero-actions,
.panel-actions,
.compare-actions,
.manual-update-actions,
.ticker-filters,
.sample-tickers {
  gap: 10px !important;
}

.top-nav a,
.panel-link,
.hero-actions a,
.project-card a,
.hero-link,
.primary-button,
.secondary-button,
.button,
button,
.text-button,
.ticker-form button,
.ticker-filters button,
.sample-tickers button,
.control-card button,
.hero-dashboard-button {
  min-height: 44px;
  padding-inline: 18px !important;
}

.status-card {
  background: rgba(8,10,15,.36) !important;
}

@media (max-width: 720px) {
  .hero,
  main,
  .section,
  .site-footer {
    width: min(100% - 28px, 1320px) !important;
  }
  .hero { margin-top: 14px; border-radius: 24px; }
  .panel,
  .manual-update,
  .controls,
  .control-card,
  .notice-card,
  .lookup-status,
  .company-section,
  .methodology-section { padding: 18px !important; }
}


/* Visual Ralph readability pass — contrast, tables, charts, 2026-06-24. */
:root {
  --surface-cyan: rgba(14, 116, 144, 0.16);
  --surface-teal: rgba(20, 184, 166, 0.13);
  --surface-violet: rgba(139, 92, 246, 0.14);
  --surface-amber: rgba(245, 158, 11, 0.13);
  --surface-rose: rgba(244, 63, 94, 0.13);
  --text-strong: #f8fafc;
  --text-readable: #dce3ee;
  --text-muted-readable: #b8c2d1;
}

.table-wrap,
.table-scroll,
.data-table-wrap,
.performance-table-wrap,
.signal-table-wrap,
.sensitivity-wrap,
.chart,
.line-chart,
.chart-card,
.forecast-chart {
  scrollbar-color: rgba(125, 211, 252, 0.58) rgba(255, 255, 255, 0.05);
}

.table-wrap,
.table-scroll,
.data-table-wrap,
.performance-table-wrap,
.signal-table-wrap {
  background:
    linear-gradient(90deg, rgba(125, 211, 252, 0.10), transparent 24px) left / 32px 100% no-repeat,
    linear-gradient(270deg, rgba(196, 181, 253, 0.14), transparent 30px) right / 40px 100% no-repeat,
    rgba(255, 255, 255, 0.025) !important;
  border-color: rgba(226, 232, 240, 0.18) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.045), 0 18px 50px rgba(0,0,0,0.24) !important;
}

.table-wrap table,
.table-scroll table,
.data-table-wrap table,
.performance-table,
.data-table,
table {
  border-collapse: separate !important;
  border-spacing: 0 !important;
  font-variant-numeric: tabular-nums lining-nums;
  background: transparent !important;
}

th,
td {
  border-bottom-color: rgba(226, 232, 240, 0.13) !important;
}

th {
  color: #dbeafe !important;
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.22), rgba(15, 23, 42, 0.42)) !important;
  text-transform: none;
  letter-spacing: 0.01em;
}

td {
  color: var(--text-readable) !important;
}

tbody tr:nth-child(even) {
  background: rgba(125, 211, 252, 0.045) !important;
}

tbody tr:hover {
  background: rgba(196, 181, 253, 0.10) !important;
}

td:not(:first-child),
.value-cell,
.sensitivity-cell,
.metric-card strong,
.card strong,
.chart-summary-item em,
.status-value,
.bar-value {
  font-variant-numeric: tabular-nums lining-nums;
}

.line-chart,
.chart-card,
.chart,
.forecast-chart {
  background:
    radial-gradient(circle at 8% 0%, rgba(125, 211, 252, 0.08), transparent 20rem),
    linear-gradient(180deg, rgba(18, 24, 36, 0.98), rgba(10, 13, 20, 0.96)) !important;
  border-color: rgba(226, 232, 240, 0.18) !important;
}

.axis-label,
.axis-title,
.axis-range,
.chart-card svg text,
.line-chart svg text,
.chart svg text,
.line-end-label text {
  fill: #dbe3ee !important;
  color: #dbe3ee !important;
  paint-order: stroke;
  stroke: rgba(8, 10, 15, 0.78);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.grid,
.line-grid,
.chart-card .axis-row line,
.chart-card .axis-column line,
.line-chart .axis-line {
  stroke: rgba(226, 232, 240, 0.18) !important;
}

.axis,
.axis-line {
  stroke: rgba(226, 232, 240, 0.34) !important;
}

.legend,
.line-legend,
.chart-legend,
.chart-help,
.chart-meta,
.axis-note,
.scale-legend,
.scale-foot {
  color: var(--text-muted-readable) !important;
}

.empty,
.empty-state,
.skeleton-line {
  color: var(--text-readable) !important;
  background: linear-gradient(135deg, rgba(125, 211, 252, 0.08), rgba(196, 181, 253, 0.07)) !important;
  border-color: rgba(125, 211, 252, 0.24) !important;
}

.status-pill,
.badge,
.classification,
.factor-pill,
.marker-help,
.rank-badge,
.warn-badge {
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
}

/* Momentum page: remove residual light cards and prevent chart label loss. */
.notice,
.manual-update,
.diagnostic-card,
.diagnostic-note,
.scenario-note,
.gate-item,
.mini-item,
.window-chip,
.performance-period-card,
.factor-method-card,
.method-item,
.metric-tile,
.rank-card,
.explain,
.disclaimer,
.viz-card,
.visual-panel,
.performance-metrics-heading,
.trend-bars {
  color: var(--ink) !important;
  background: linear-gradient(145deg, rgba(125,211,252,0.08), rgba(255,255,255,0.035)) !important;
  border-color: rgba(226,232,240,0.14) !important;
}
.notice:nth-of-type(2n),
.viz-card:nth-child(2n),
.diagnostic-card:nth-child(2n),
.performance-period-card:nth-child(2n) {
  background: linear-gradient(145deg, rgba(196,181,253,0.10), rgba(255,255,255,0.035)) !important;
}
.manual-update,
.controls { background: linear-gradient(135deg, rgba(14,116,144,0.16), rgba(139,92,246,0.10)) !important; }
.manual-update p,
.notice,
.diagnostic-note,
.scenario-note,
.explain ul,
.disclaimer,
.gate-item small,
.mini-item small,
.window-chip small,
.method-summary,
.method-item small,
.performance-metrics-heading p { color: var(--text-muted-readable) !important; }
.bar-row.is-selected,
.bar-row.is-best,
.rank-card.is-selected {
  background: linear-gradient(90deg, rgba(251,191,36,0.16), rgba(125,211,252,0.08)) !important;
  border-color: rgba(251,191,36,0.36) !important;
}
.bar-label,
.bar-value,
.metric-name,
.series-name,
.window-chip strong,
.performance-period-card h5 { color: var(--text-strong) !important; }
.trend-bars { min-width: min(100%, 720px); padding-bottom: 0.75rem; }
.trend-label { color: #c8d3e2 !important; font-size: 0.72rem !important; }
.line-chart svg { min-width: 620px; }
@media (max-width: 640px) {
  .trend-chart,
  .line-chart { overflow-x: auto; }
  .bar-row, .compact-bars .bar-row { align-items: stretch; }
}

/* Visual Ralph follow-up: nested labels, legends, and compact rows, 2026-06-25. */
.bar-row,
.compact-bars .bar-row,
.chart-summary-item,
.gate-item,
.mini-item,
.performance-period-card,
.window-chip,
.legend span,
.line-legend span,
.chart-legend span,
.badge,
.card-badge {
  background: linear-gradient(135deg, rgba(15,23,42,0.82), rgba(30,41,59,0.64)) !important;
  border-color: rgba(226,232,240,0.16) !important;
  color: var(--text-readable) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.055) !important;
}
.bar-row:nth-child(3n+1),
.chart-summary-item:nth-child(3n+1),
.window-chip:nth-child(3n+1) {
  background: linear-gradient(135deg, rgba(14,116,144,0.18), rgba(15,23,42,0.84)) !important;
}
.bar-row:nth-child(3n+2),
.chart-summary-item:nth-child(3n+2),
.window-chip:nth-child(3n+2) {
  background: linear-gradient(135deg, rgba(139,92,246,0.16), rgba(15,23,42,0.84)) !important;
}
.bar-row strong,
.compact-bars strong,
.chart-summary-item strong,
.gate-item strong,
.mini-item strong,
.performance-period-card h5,
.window-chip strong { color: #f8fafc !important; }
.bar-row small,
.compact-bars small,
.chart-summary-item small,
.gate-item small,
.mini-item small,
.performance-period-card small,
.window-chip small,
.legend,
.line-legend,
.chart-legend { color: #bac7d7 !important; }
.bar-track { background: rgba(148,163,184,0.20) !important; }
.legend-dot,
.chart-legend .legend-dot { box-shadow: 0 0 0 1px rgba(255,255,255,0.24), 0 0 14px currentColor !important; }

/* Readable dark research cockpit refresh — 2026-06-26.
   Keep the dark concept, but reduce over-black surfaces and raise text/chart contrast. */
:root {
  color-scheme: dark;
  --bg: #111827;
  --panel: #182235;
  --card: #1d2940;
  --surface: #182235;
  --surface-soft: #24324c;
  --ink: #f8fafc;
  --muted: #c5d0df;
  --line: rgba(203, 213, 225, 0.28);
  --accent: #60a5fa;
  --accent-2: #7dd3fc;
  --accent-soft: rgba(96, 165, 250, 0.18);
  --good: #74e0a3;
  --warn: #f8c66a;
  --danger: #fb7185;
  --shadow: 0 18px 46px rgba(0, 0, 0, 0.28);
}

html { background: #111827 !important; }

body {
  color: var(--ink) !important;
  background:
    radial-gradient(circle at 14% -6%, rgba(96, 165, 250, 0.22), transparent 34rem),
    radial-gradient(circle at 88% 4%, rgba(125, 211, 252, 0.14), transparent 30rem),
    linear-gradient(180deg, #172033 0%, #111827 54%, #121a2a 100%) !important;
}

body::before {
  opacity: .38;
  background-size: 88px 88px;
}

.hero {
  background:
    radial-gradient(circle at 78% -12%, rgba(125, 211, 252, .22), transparent 28rem),
    linear-gradient(135deg, #22304a 0%, #172033 58%, #132034 100%) !important;
  border-bottom: 1px solid rgba(203, 213, 225, .22);
  box-shadow: 0 22px 70px rgba(0, 0, 0, .28) !important;
}

.hero-copy,
.panel-heading p,
.notice,
.manual-update p,
.card small,
.control-hint,
.chart-meta,
#manual-update-status,
.line-legend,
.scenario-note,
.diagnostic-note,
.disclaimer,
footer {
  color: var(--muted) !important;
}

.hero-copy { opacity: 1 !important; }

.status-card,
.notice,
.manual-update,
.controls,
.card,
.panel,
.disclaimer,
.viz-card,
.diagnostic-card,
.performance-period-card,
.window-chip,
.factor-method-card,
.method-item,
.explain {
  background: linear-gradient(180deg, rgba(29, 41, 64, .98), rgba(24, 34, 53, .98)) !important;
  border-color: var(--line) !important;
  box-shadow: var(--shadow) !important;
}

.manual-update,
.visual-panel {
  background:
    linear-gradient(180deg, rgba(34, 48, 74, .98), rgba(24, 34, 53, .98)) !important;
}

.controls-enhanced {
  display: grid;
  grid-template-columns: minmax(280px, .9fr) minmax(320px, 1.35fr);
  gap: 1rem;
  padding: 0;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

.control-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .9rem;
  padding: 1.1rem;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(29, 41, 64, .98), rgba(24, 34, 53, .98));
  box-shadow: var(--shadow);
  min-width: 0;
}

.control-group-heading {
  grid-column: 1 / -1;
}

.control-group-heading h2 {
  margin: 0;
  font-size: 1.05rem;
  color: var(--ink);
}

label { color: #d8e2ef !important; }

select,
input {
  color: #f8fafc !important;
  background: #111827 !important;
  border-color: rgba(203, 213, 225, .34) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}

select:focus,
input:focus,
button:focus,
a:focus {
  outline: 3px solid rgba(125, 211, 252, .58) !important;
  outline-offset: 2px;
}

.unit { color: #d8e2ef !important; font-weight: 900; }

.preset-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}

.preset-row button {
  border: 1px solid rgba(125, 211, 252, .35);
  border-radius: 999px;
  color: #dff6ff;
  background: rgba(96, 165, 250, .14);
  padding: .5rem .72rem;
  font: inherit;
  font-size: .82rem;
  font-weight: 900;
  cursor: pointer;
}

.preset-row button:hover { background: rgba(96, 165, 250, .26); }

.scenario-live-summary {
  grid-column: 1 / -1;
  margin: 0;
  padding: .78rem .9rem;
  border: 1px solid rgba(125, 211, 252, .28);
  border-radius: 16px;
  color: #e0f2fe;
  background: rgba(96, 165, 250, .12);
  line-height: 1.6;
  font-weight: 800;
}

.card strong,
.panel-heading h2,
.viz-card h3,
.diagnostic-card h3,
.performance-period-card h5,
.metric-name,
th,
td,
.window-chip strong {
  color: var(--ink) !important;
}

table,
.line-chart,
.trend-bars,
.window-chip,
.performance-period-card,
.performance-period-card h5,
.gate-item,
.mini-item,
.factor-method-card,
.method-item,
.empty-state,
.scenario-note,
.diagnostic-note,
.code-pill {
  background: #111827 !important;
  border-color: var(--line) !important;
}

th {
  background: #22304a !important;
  color: #e5edf7 !important;
}

tbody tr:hover { background: rgba(96, 165, 250, .10) !important; }

.bar-track { background: #334155 !important; }
.bar-fill { background: linear-gradient(90deg, #60a5fa, #7dd3fc) !important; }
.bar-fill.negative { background: linear-gradient(90deg, #fb7185, #fda4af) !important; }
.bar-row.is-selected { background: rgba(96, 165, 250, .16) !important; border-color: rgba(96, 165, 250, .48) !important; }
.bar-row.is-best:not(.is-selected) { background: rgba(116, 224, 163, .14) !important; border-color: rgba(116, 224, 163, .44) !important; }

.line-chart svg { background: transparent !important; }
.line-grid { stroke: rgba(203, 213, 225, .24) !important; }
.axis-line { stroke: rgba(226, 232, 240, .54) !important; }
.axis-label { fill: #d8e2ef !important; }
.axis-title { fill: #eff6ff !important; }
.line-path.selected { stroke: #7dd3fc !important; }
.line-path.best { stroke: #74e0a3 !important; }
.line-path.benchmark { stroke: #c4b5fd !important; }
.legend-dot { background: #7dd3fc !important; }
.legend-dot.best { background: #74e0a3 !important; }
.legend-dot.benchmark { background: #c4b5fd !important; }
.trend-fill { background: linear-gradient(180deg, #7dd3fc, #60a5fa) !important; }

.positive { color: #86efac !important; }
.negative { color: #fda4af !important; }
.badge { background: rgba(96, 165, 250, .18) !important; color: #dff6ff !important; }
.gate-item.pass { background: rgba(116, 224, 163, .12) !important; border-color: rgba(116, 224, 163, .34) !important; }
.gate-item.block { background: rgba(248, 198, 106, .12) !important; border-color: rgba(248, 198, 106, .38) !important; }

@media (max-width: 1180px) {
  .controls-enhanced { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .control-group { grid-template-columns: 1fr; }
  .preset-row button { flex: 1 1 auto; }
}

/* Visual Ralph family-aligned dark palette — 2026-06-27.
   Align with connected Pages dashboards: shared navy/blue/cyan accents,
   port-like near-black surfaces, and stronger readable foregrounds. */
:root {
  color-scheme: dark;
  --bg: #080a0f;
  --panel: #12161e;
  --card: #171d29;
  --surface: #12161e;
  --surface-strong: #0d1118;
  --surface-soft: #1f2430;
  --ink: #f4f7fb;
  --muted: #c5cfdd;
  --line: rgba(226, 232, 240, 0.18);
  --accent: #7dd3fc;
  --accent-2: #44b3ff;
  --accent-soft: rgba(36, 87, 214, 0.20);
  --good: #86efac;
  --warn: #fbbf24;
  --danger: #fb7185;
  --shadow: 0 24px 72px rgba(0, 0, 0, 0.36);
}

html { background: var(--bg) !important; }

body {
  line-height: 1.7;
  color: var(--ink) !important;
  background:
    radial-gradient(circle at 12% -10%, rgba(36, 87, 214, 0.18), transparent 34rem),
    radial-gradient(circle at 88% 2%, rgba(68, 179, 255, 0.12), transparent 30rem),
    linear-gradient(180deg, #0d1320 0%, #080a0f 50%, #0b1018 100%) !important;
}

body::before {
  opacity: .28;
  background-size: 96px 96px;
}

.hero {
  background:
    radial-gradient(circle at 82% -12%, rgba(68, 179, 255, .22), transparent 29rem),
    linear-gradient(135deg, #132033 0%, #173a95 64%, #2457d6 100%) !important;
  border-bottom: 1px solid rgba(226, 232, 240, .16);
  box-shadow: 0 24px 76px rgba(0, 0, 0, .38) !important;
}

.hero .eyebrow { color: #bfdbfe !important; }
.hero-copy { opacity: 1 !important; color: #dbeafe !important; }

.notice,
.manual-update,
.controls,
.card,
.panel,
.disclaimer,
.viz-card,
.diagnostic-card,
.performance-period-card,
.window-chip,
.explain,
.status-card,
.control-group {
  color: var(--ink) !important;
  background:
    linear-gradient(180deg, rgba(23, 29, 41, .97), rgba(18, 22, 30, .97)) !important;
  border-color: var(--line) !important;
  box-shadow: var(--shadow) !important;
}

.manual-update,
.visual-panel,
.control-group-backtest {
  background:
    radial-gradient(circle at 100% 0%, rgba(36, 87, 214, .14), transparent 22rem),
    linear-gradient(180deg, rgba(31, 36, 48, .98), rgba(18, 22, 30, .98)) !important;
}

.controls-enhanced {
  display: grid;
  grid-template-columns: minmax(280px, .9fr) minmax(320px, 1.35fr);
  gap: 1rem;
  padding: 0;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

.control-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .9rem;
  padding: 1.1rem;
  border-radius: 24px;
  min-width: 0;
}

.control-group-heading { grid-column: 1 / -1; }
.control-group-heading h2 { margin: 0; font-size: 1.05rem; color: var(--ink); }

.hero-copy,
.panel-heading p,
.notice,
.manual-update p,
.card small,
.control-hint,
.chart-meta,
#manual-update-status,
.line-legend,
.scenario-note,
.diagnostic-note,
.disclaimer,
footer,
.gate-item small,
.mini-item small,
.window-chip small,
.performance-metrics-heading p {
  color: var(--muted) !important;
}

label { color: #dbe7f4 !important; }
.unit { color: #dbe7f4 !important; font-weight: 900; }

select,
input {
  color: #f8fafc !important;
  background: #0d1118 !important;
  border-color: rgba(226, 232, 240, .26) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
}

select:hover,
input:hover { border-color: rgba(125, 211, 252, .48) !important; }

select:focus,
input:focus,
button:focus,
a:focus {
  outline: 3px solid rgba(125, 211, 252, .62) !important;
  outline-offset: 2px;
}

.preset-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}

.preset-row button,
.button.secondary {
  border: 1px solid rgba(125, 211, 252, .34);
  border-radius: 999px;
  color: #e0f2fe;
  background: rgba(36, 87, 214, .18);
  padding: .5rem .72rem;
  font: inherit;
  font-size: .82rem;
  font-weight: 900;
  cursor: pointer;
}

.preset-row button:hover,
.button.secondary:hover { background: rgba(36, 87, 214, .30); }
.button.primary { background: #2457d6 !important; color: #ffffff !important; box-shadow: 0 14px 28px rgba(36, 87, 214, .28) !important; }

.scenario-live-summary {
  grid-column: 1 / -1;
  margin: 0;
  padding: .78rem .9rem;
  border: 1px solid rgba(125, 211, 252, .30);
  border-radius: 16px;
  color: #e0f2fe;
  background: rgba(36, 87, 214, .16);
  line-height: 1.6;
  font-weight: 800;
}

.card strong,
.panel-heading h2,
.viz-card h3,
.diagnostic-card h3,
.performance-period-card h5,
.metric-name,
th,
td,
.window-chip strong,
.bar-label,
.bar-value {
  color: var(--ink) !important;
}

table,
.line-chart,
.trend-bars,
.performance-period-card,
.performance-period-card h5,
.gate-item,
.mini-item,
.factor-method-card,
.method-item,
.empty-state,
.scenario-note,
.diagnostic-note,
.code-pill,
.table-wrap {
  background: #0d1118 !important;
  border-color: rgba(226, 232, 240, .18) !important;
}

th {
  background: linear-gradient(180deg, rgba(36, 87, 214, .28), rgba(13, 17, 24, .92)) !important;
  color: #e5edf7 !important;
}

td { color: #dce6f2 !important; }
tbody tr:nth-child(even) { background: rgba(255, 255, 255, .025) !important; }
tbody tr:hover { background: rgba(36, 87, 214, .12) !important; }

.bar-row,
.compact-bars .bar-row,
.chart-summary-item,
.legend span,
.line-legend span,
.chart-legend span {
  background: rgba(13, 17, 24, .64) !important;
  border-color: rgba(226, 232, 240, .14) !important;
}

.bar-track { background: rgba(148, 163, 184, .22) !important; }
.bar-fill { background: linear-gradient(90deg, #2457d6, #44b3ff) !important; }
.bar-fill.negative { background: linear-gradient(90deg, #fb7185, #fda4af) !important; }
.bar-row.is-selected { background: rgba(36, 87, 214, .18) !important; border-color: rgba(68, 179, 255, .46) !important; }
.bar-row.is-best:not(.is-selected) { background: rgba(134, 239, 172, .12) !important; border-color: rgba(134, 239, 172, .36) !important; }

.line-chart {
  background:
    radial-gradient(circle at 8% 0%, rgba(36, 87, 214, .10), transparent 20rem),
    linear-gradient(180deg, #111827, #0d1118) !important;
}
.line-chart svg { background: transparent !important; }
.line-grid { stroke: rgba(226, 232, 240, .18) !important; }
.axis-line { stroke: rgba(226, 232, 240, .46) !important; }
.axis-label { fill: #cbd5e1 !important; }
.axis-title { fill: #f1f5f9 !important; }
.line-path.selected { stroke: #44b3ff !important; }
.line-path.best { stroke: #86efac !important; }
.line-path.benchmark { stroke: #c4b5fd !important; }
.legend-dot { background: #44b3ff !important; }
.legend-dot.best { background: #86efac !important; }
.legend-dot.benchmark { background: #c4b5fd !important; }
.trend-fill { background: linear-gradient(180deg, #44b3ff, #2457d6) !important; }

.positive { color: #86efac !important; }
.negative { color: #fda4af !important; }
.badge { background: rgba(36, 87, 214, .20) !important; color: #e0f2fe !important; }
.gate-item.pass { background: rgba(134, 239, 172, .10) !important; border-color: rgba(134, 239, 172, .32) !important; }
.gate-item.block { background: rgba(251, 191, 36, .10) !important; border-color: rgba(251, 191, 36, .34) !important; }

.manual-update-actions .button.secondary,
.manual-update-actions .code-pill {
  background: #0d1118 !important;
  color: #f4f8fd !important;
}

p,
li,
dd,
td,
small { line-height: 1.68; }

@media (max-width: 1180px) {
  .controls-enhanced { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .control-group { grid-template-columns: 1fr; }
  .preset-row button { flex: 1 1 auto; }
}

/* Shared readability jump nav — UI-only, 2026-06-29. */
.page-jump-nav {
  position: fixed;
  right: clamp(14px, 2vw, 26px);
  bottom: clamp(16px, 3vw, 30px);
  z-index: 1000;
  display: grid;
  gap: 8px;
  pointer-events: none;
}
.page-jump-nav a {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 64px;
  min-height: 40px;
  padding: 9px 12px;
  border: 1px solid rgba(226, 232, 240, 0.22);
  border-radius: 999px;
  color: #f8fafc !important;
  background: rgba(10, 13, 20, 0.82) !important;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.34), inset 0 1px 0 rgba(255,255,255,0.08);
  text-decoration: none;
  font-size: 0.82rem;
  font-weight: 900;
  letter-spacing: -0.01em;
  backdrop-filter: blur(14px);
}
.page-jump-nav a:hover,
.page-jump-nav a:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(125, 211, 252, 0.55);
  background: rgba(20, 29, 43, 0.94) !important;
}
#page-bottom { scroll-margin-top: 24px; }
@media (max-width: 640px) {
  .page-jump-nav { right: 10px; bottom: 10px; gap: 6px; }
  .page-jump-nav a { min-width: 54px; min-height: 36px; padding: 8px 10px; font-size: 0.76rem; }
}

/* Readability pass support — moved cautions and dense comparison cells, 2026-06-29. */
.moved-notice {
  margin-top: 28px !important;
  scroll-margin-top: 28px;
}
.weight-matrix-cell {
  min-width: 138px;
  vertical-align: top;
}
.weight-matrix-cell strong,
.weight-matrix-cell small {
  display: block;
}
.weight-matrix-cell strong {
  color: var(--text-strong, var(--ink, #f8fafc)) !important;
  font-variant-numeric: tabular-nums lining-nums;
}
.weight-matrix-cell small {
  margin-top: 4px;
  color: var(--text-muted-readable, var(--muted, #b8c2d1)) !important;
  line-height: 1.35;
}


/* Mobile status wrapping — UI-only, 2026-06-29. */
@media (max-width: 640px) {
  .status-card { min-width: 0 !important; width: 100%; overflow: hidden; }
  .status-line { grid-template-columns: minmax(0, 1fr); gap: .2rem; }
  .status-label, .status-value { min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
}

/* Mobile copy overflow guard — UI-only, 2026-06-29. */
@media (max-width: 640px) {
  body { word-break: normal; overflow-wrap: anywhere; }
  .hero, main, footer { padding-left: 14px; padding-right: 14px; }
  .hero-copy, .hero p, .panel-heading p, .helper, .scenario-note, .status-value { max-width: 100%; overflow-wrap: anywhere; word-break: normal; }
}

/* Mobile viewport width clamp — UI-only, 2026-06-29. */
@media (max-width: 640px) {
  .hero, main, .section, .site-footer {
    width: calc(100vw - 28px) !important;
    max-width: calc(100vw - 28px) !important;
    margin-left: auto !important;
    margin-right: auto !important;
    overflow: hidden;
  }
  .controls, .panel, .card, .viz-card, .diagnostic-card, .status-card { max-width: 100%; }
  select, input, button { min-width: 0; max-width: 100%; }
}

/* Mobile Korean text wrapping hardening — UI-only, 2026-06-29. */
@media (max-width: 640px) {
  .hero, main, footer, .panel, .notice, .card, .status-card, .disclaimer {
    min-width: 0;
    max-width: 100%;
  }
  .hero h1, .hero p, .hero-copy, .panel-heading p, .notice, .status-value, .card strong, .card small, .helper, .scenario-note {
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
    line-break: anywhere;
  }
  .hero h1 {
    font-size: clamp(1.85rem, 8.8vw, 2.55rem);
    line-height: 1.14;
  }
}

/* Focused mobile overflow fix — UI-only, 2026-06-29. */
@media (max-width: 640px) {
  html, body {
    width: 100%;
    max-width: 100%;
    overflow-x: hidden !important;
  }
  body {
    display: block;
  }
  .hero {
    display: block !important;
    width: calc(100% - 24px) !important;
    max-width: calc(100% - 24px) !important;
    margin: 12px auto 0 !important;
    padding: 22px 14px !important;
    overflow: hidden !important;
  }
  .hero > *, .hero-main, .hero-copy, .hero-actions, .status-card, .controls, .control-group, .panel, .cards, .card {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
  }
  .hero h1 {
    max-width: 100%;
    font-size: clamp(1.65rem, 7.4vw, 2.2rem) !important;
    line-height: 1.18 !important;
    letter-spacing: -0.045em !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
  }
  .hero p, .hero-copy, .status-value, .control-hint, .helper, .scenario-note {
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
    line-break: anywhere;
  }
  .hero-actions a, .hero-link, .button, button {
    white-space: normal !important;
  }
}

"""

JS_CONTENT = r"""const MANUAL_UPDATE_WORKFLOW_URL = 'https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml';
const MANUAL_UPDATE_COMMAND = 'gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main';

const FACTOR_METHOD_OVERRIDES = {
  "mom_12_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-273] - 1",
    "description": "Traditional 12-1 cross-sectional total return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_9_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-210] - 1",
    "description": "Nine-month skipped return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_6_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-147] - 1",
    "description": "Traditional 6-1 cross-sectional total return momentum.",
    "validation": "Manual shifted-return and no-lookahead tests."
  },
  "mom_12_2": {
    "category": "traditional",
    "formula": "P[t-42] / P[t-294] - 1",
    "description": "Twelve-month momentum with a two-month skip to reduce reversal contamination.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_3_1": {
    "category": "traditional",
    "formula": "P[t-21] / P[t-84] - 1",
    "description": "Traditional 3-1 skipped return momentum.",
    "validation": "Independent shifted-return and no-lookahead tests."
  },
  "mom_10d": {
    "category": "recent",
    "formula": "P[t] / P[t-10] - 1",
    "description": "Ten-trading-day short-horizon momentum with high-turnover warning.",
    "validation": "Literal golden-vector simple-return tests and turnover warning audit."
  },
  "mom_6m_unskipped": {
    "category": "recent",
    "formula": "P[t] / P[t-126] - 1",
    "description": "Six-month recent momentum without a skip window.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_3m": {
    "category": "recent",
    "formula": "P[t] / P[t-63] - 1",
    "description": "Three-month recent momentum without skip month.",
    "validation": "Simple-return fixture tests."
  },
  "mom_2m": {
    "category": "recent",
    "formula": "P[t] / P[t-42] - 1",
    "description": "Two-month short-horizon momentum for fast leadership changes.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_2_1": {
    "category": "recent",
    "formula": "P[t-21] / P[t-63] - 1",
    "description": "Two-month momentum that skips the most recent month.",
    "validation": "Independent raw-shift golden tests."
  },
  "mom_6m": {
    "category": "recent",
    "formula": "P[t-10] / P[t-136] - 1",
    "description": "Six-month momentum ending ten trading days before the signal date to avoid very recent reversal noise.",
    "validation": "Independent shifted-return and no-lookahead tests; intentionally distinct from mom_6m_unskipped."
  },
  "mom_12m": {
    "category": "recent",
    "formula": "P[t] / P[t-252] - 1",
    "description": "Twelve-month simple momentum without skip month.",
    "validation": "Independent simple-return and no-lookahead tests."
  },
  "mom_1m": {
    "category": "recent",
    "formula": "P[t] / P[t-21] - 1",
    "description": "One-month short-horizon momentum.",
    "validation": "Simple-return fixture tests."
  },
  "multi_horizon": {
    "category": "composite",
    "formula": "0.15*1m + 0.25*3m(skip5) + 0.30*6m(skip10) + 0.30*12m(skip21)",
    "description": "Weighted 1/3/6/12-month multi-horizon momentum composite.",
    "validation": "Component helper tests plus output audit."
  },
  "vol_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / annualized_vol_63d",
    "description": "Six-month momentum scaled by recent annualized volatility.",
    "validation": "Division-by-zero and finite coverage audit."
  },
  "risk_adjusted": {
    "category": "risk_adjusted",
    "formula": "annualized_mean_return_126d / annualized_vol_126d",
    "description": "Rolling Sharpe-like annualized return divided by volatility.",
    "validation": "Rolling mean/vol helper tests."
  },
  "downside_risk_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / annualized_downside_vol_126d",
    "description": "Momentum scaled by downside volatility only.",
    "validation": "Downside fixture tests and finite audit."
  },
  "dual_momentum": {
    "category": "trend",
    "formula": "6m relative momentum penalized when price < MA200",
    "description": "Relative momentum penalized when absolute trend is below the 200-day average.",
    "validation": "Trend penalty and no-lookahead audit."
  },
  "ma_trend": {
    "category": "trend",
    "formula": "P/MA200 - 1 + 0.5*(MA50/MA200 - 1)",
    "description": "Trend persistence from price/MA200 and MA50/MA200 structure.",
    "validation": "Moving-average fixture tests."
  },
  "time_series_trend": {
    "category": "trend",
    "formula": "I(P>MA20)+I(MA20>MA100)+I(MA100>MA200)",
    "description": "Discrete time-series trend stack across short/intermediate/long averages.",
    "validation": "Bounded 0..3 output audit."
  },
  "drawdown_aware": {
    "category": "drawdown",
    "formula": "6m(skip10) + P/rolling_high_126 - 1",
    "description": "Six-month momentum penalized by recent drawdown from rolling high.",
    "validation": "Drawdown sign and no-lookahead audit."
  },
  "high_52w": {
    "category": "drawdown",
    "formula": "P / rolling_high_252 - 1",
    "description": "Closeness to 52-week high; less negative is stronger.",
    "validation": "Manual rolling-high fixture tests."
  },
  "high_26w": {
    "category": "drawdown",
    "formula": "P / rolling_high_126 - 1",
    "description": "Closeness to a 26-week high for intermediate breakout confirmation.",
    "validation": "Independent rolling-high golden tests."
  },
  "breakout_63d": {
    "category": "breakout",
    "formula": "P/rolling_high_63 - 1 + 0.5*1m",
    "description": "Recent breakout pressure with one-month confirmation.",
    "validation": "Rolling-high plus 1m fixture tests."
  },
  "breakout_126d": {
    "category": "breakout",
    "formula": "P/rolling_high_126 - 1 + 0.5*3m",
    "description": "Intermediate breakout pressure with three-month confirmation.",
    "validation": "Independent rolling-high golden tests."
  },
  "reversal_adjusted": {
    "category": "reversal",
    "formula": "12-1 momentum - 0.35*1m momentum",
    "description": "12-1 momentum adjusted for short-term reversal risk.",
    "validation": "Component helper tests plus no-lookahead audit."
  },
  "acceleration": {
    "category": "acceleration",
    "formula": "3m momentum - 0.5*6-1 momentum",
    "description": "Momentum acceleration toward recent leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "short_acceleration": {
    "category": "acceleration",
    "formula": "1m momentum - 0.5*3m momentum",
    "description": "Short-horizon acceleration signal for very recent leadership surges.",
    "validation": "Independent raw-shift golden tests."
  },
  "decay_adjusted": {
    "category": "acceleration",
    "formula": "6m(skip10) - 0.25*abs(1m momentum)",
    "description": "Six-month momentum penalized when very recent moves look overextended.",
    "validation": "Independent raw-shift golden tests."
  },
  "consistency": {
    "category": "quality",
    "formula": "6m(skip10) * rolling_positive_return_ratio_126d",
    "description": "Rewards momentum earned consistently across days.",
    "validation": "Positive-ratio fixture tests."
  },
  "persistent_12_1": {
    "category": "quality",
    "formula": "12m(skip21) * positive_daily_return_ratio_252d(skip21)",
    "description": "Long-horizon skipped momentum scaled by the share of positive daily returns in the skipped formation window.",
    "validation": "Positive-ratio and no-lookahead tests."
  },
  "low_vol_momentum": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) - annualized_vol_63d",
    "description": "Momentum penalized by high recent volatility.",
    "validation": "Low-vol ranking fixture tests."
  },
  "stability_adjusted": {
    "category": "risk_adjusted",
    "formula": "6m(skip10) / (1 + annualized_vol_126d)",
    "description": "Six-month momentum damped by one-year realized volatility from price returns.",
    "validation": "Independent volatility golden tests."
  },
  "relative_strength_6m": {
    "category": "cross_sectional",
    "formula": "cross-sectional percentile_rank(6m(skip10))",
    "description": "Six-month relative-strength percentile within the eligible universe.",
    "validation": "Cross-sectional rank audit."
  },
  "trend_quality": {
    "category": "quality",
    "formula": "P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126",
    "description": "Combines trend slope with smoothness of returns.",
    "validation": "Rolling helper and finite audit."
  },
  "gap_resistant": {
    "category": "robust",
    "formula": "compound clipped daily returns over 126d",
    "description": "Momentum using clipped daily returns to reduce single-gap dominance.",
    "validation": "Clipped-return fixture tests."
  },
  "winsorized_skip": {
    "category": "robust",
    "formula": "compound clipped daily returns over 126d after 10d skip",
    "description": "Skipped six-month momentum using winsorized daily returns to reduce gap dominance.",
    "validation": "Independent clipped-return golden tests."
  },
  "price_efficiency": {
    "category": "quality",
    "formula": "6m(skip10) * |P/P[t-126]-1| / sum_126(|daily_return|)",
    "description": "Rewards six-month momentum that traveled a direct, low-chop price path.",
    "validation": "Path-efficiency fixture tests and division-by-zero audit."
  },
  "range_position": {
    "category": "range",
    "formula": "6m(skip10) + (P-low_126)/(high_126-low_126) - 0.5",
    "description": "Combines six-month momentum with where price sits inside its trailing range.",
    "validation": "Rolling-range fixture tests and flat-range audit."
  },
  "range_position_252d": {
    "category": "range",
    "formula": "12m(skip21) + (P-low_252)/(high_252-low_252) - 0.5",
    "description": "Combines long-horizon skipped momentum with position inside a 52-week range.",
    "validation": "Independent rolling-range golden tests."
  },
  "median_return_3m": {
    "category": "robust",
    "formula": "median(daily_return, 63d) * 63",
    "description": "Three-month median daily return momentum to reduce outlier sensitivity.",
    "validation": "Median-return golden-vector and outlier-gap tests."
  },
  "median_return_6m": {
    "category": "robust",
    "formula": "median(daily_return, 126d) * 126",
    "description": "Six-month median daily return momentum to reduce outlier sensitivity.",
    "validation": "Median-return golden-vector and no-lookahead tests."
  },
  "winsorized_3m": {
    "category": "robust",
    "formula": "compound clipped [-8%, +8%] daily returns over 63d",
    "description": "Three-month winsorized compounded momentum.",
    "validation": "Winsorized golden-vector and outlier-gap tests."
  },
  "winsorized_12m": {
    "category": "robust",
    "formula": "compound clipped [-8%, +8%] daily returns over 252d",
    "description": "Twelve-month winsorized compounded momentum.",
    "validation": "Winsorized no-lookahead and edge-case tests."
  },
  "vol_adjusted_3m": {
    "category": "risk_adjusted",
    "formula": "3m simple momentum / annualized_vol_63d",
    "description": "Three-month momentum scaled by recent annualized volatility.",
    "validation": "Division-by-zero and finite coverage audit."
  },
  "vol_adjusted_12m": {
    "category": "risk_adjusted",
    "formula": "12-1 momentum / annualized_vol_126d",
    "description": "Twelve-minus-one momentum scaled by intermediate volatility.",
    "validation": "Division-by-zero and no-lookahead audit."
  },
  "downside_adjusted_12m": {
    "category": "risk_adjusted",
    "formula": "12-1 momentum / annualized_downside_vol_252d",
    "description": "Twelve-minus-one momentum scaled by downside volatility.",
    "validation": "Downside risk edge-case tests."
  },
  "ma_slope_50": {
    "category": "trend",
    "formula": "MA50[t] / MA50[t-21] - 1",
    "description": "One-month slope of the 50-day moving average.",
    "validation": "Moving-average slope fixture tests."
  },
  "price_vs_ma200": {
    "category": "trend",
    "formula": "P / MA200 - 1",
    "description": "Distance of price above/below the 200-day moving average.",
    "validation": "Moving-average fixture tests."
  },
  "ma_stack_quality": {
    "category": "trend",
    "formula": "I(P>MA20)+I(MA20>MA50)+I(MA50>MA100)+I(MA100>MA200)",
    "description": "Four-step moving-average stack quality score.",
    "validation": "Bounded 0..4 output and no-lookahead audit."
  },
  "breakout_20d": {
    "category": "breakout",
    "formula": "P/rolling_high_20 - 1 + 0.5*10d",
    "description": "Short breakout proximity with ten-day confirmation.",
    "validation": "Rolling-high golden-vector tests."
  },
  "accel_1m_vs_3m": {
    "category": "acceleration",
    "formula": "1m momentum - 3m momentum",
    "description": "Acceleration from three-month to one-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "accel_3m_vs_6m": {
    "category": "acceleration",
    "formula": "3m momentum - 6m momentum",
    "description": "Acceleration from six-month to three-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "accel_6m_vs_12m": {
    "category": "acceleration",
    "formula": "6m momentum - 12m momentum",
    "description": "Acceleration from twelve-month to six-month leadership.",
    "validation": "Manual acceleration fixture tests."
  },
  "ulcer_adjusted": {
    "category": "drawdown",
    "formula": "6m(skip10) / sqrt(mean(drawdown_126^2, 126d))",
    "description": "Momentum scaled by Ulcer-style drawdown severity.",
    "validation": "Drawdown denominator and finite audit."
  },
  "smooth_return_6m": {
    "category": "quality",
    "formula": "6m simple momentum - rolling_std_daily_return_126d",
    "description": "Six-month return momentum penalized by daily return roughness.",
    "validation": "Smoothness edge-case tests."
  },
  "residual_12_1": {
    "category": "cross_sectional",
    "formula": "sum_252(return shifted21) - beta_252_to_equal_weight_market * sum_252(market_return shifted21)",
    "description": "Twelve-minus-one beta-neutral residual momentum versus the equal-weight candidate-universe proxy.",
    "validation": "Rolling beta residual formula, rank-distinctness, and no-lookahead tests."
  },
  "excess_ir_6m": {
    "category": "cross_sectional",
    "formula": "annualized_mean(excess_return_126d) / annualized_tracking_error_126d",
    "description": "Six-month information-ratio style momentum versus the equal-weight candidate universe.",
    "validation": "Tracking-error denominator and no-lookahead tests."
  },
  "up_down_capture_6m": {
    "category": "asymmetry",
    "formula": "mean(return | market_up,126d) - abs(mean(return | market_down,126d))",
    "description": "Rewards stocks that participate on up-market days without giving back as much on down-market days.",
    "validation": "Market-up/down conditioning and finite-coverage tests."
  },
  "tail_resilient_6m": {
    "category": "tail_risk",
    "formula": "6m(skip10) + q05(daily_return,126d)",
    "description": "Six-month skipped momentum penalized by poor left-tail daily returns.",
    "validation": "Rolling quantile edge-case and no-lookahead tests."
  },
  "jump_excluded_6m": {
    "category": "robust",
    "formula": "sum_126(daily_return shifted10) - max_126(daily_return shifted10)",
    "description": "Formation-window momentum that removes the single largest daily jump to reduce one-day gap dominance.",
    "validation": "Independent shifted-return and outlier-resistance tests."
  },
  "high_persistence_6m": {
    "category": "quality",
    "formula": "mean_63(I(P >= 0.98*rolling_high_126))",
    "description": "Fraction of recent days spent near a six-month high, capturing persistent leadership rather than one-day proximity.",
    "validation": "Rolling-high persistence and no-lookahead tests."
  }
};

const DASHBOARD_INPUT_DEFAULTS = {
  window: '1Y',
  lookbackMonths: 12,
  topN: 20,
  maxWeightPercent: 50,
  rebalanceFrequency: 'ME',
  transactionCostBps: 5,
  slippageBps: 5,
};

const state = {
  data: null,
  activeRunIndex: 0,
  hasUserSelectedFactor: false,
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
          status.textContent = '저장소 쓰기 권한이 있는 GitHub 계정으로 Run workflow를 눌러 실행 시점의 최신 제공자 데이터 재실행을 시작하세요.';
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
const joinReasonList = (value) => {
  if (Array.isArray(value)) return value.map(textValue).filter((item) => item !== '-').join(', ');
  const text = textValue(value);
  return text === '-' ? '' : text;
};

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
    'yahoo-chart-fallback': 'Yahoo chart 조정종가 보강 데이터',
    'nasdaq-latest-repair': 'Nasdaq 최신 종가 보강 데이터',
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
  return summary.recommendation_output_key === 'recommendations'
    && summary.research_only === false
    && summary.recommendation_output_available === true
    && summary.tradable_output_available === true
    && summary.current_recommendations_available === true
    && summary.tradable_recommendations_available === true
    && summary.same_run_factor_selection_blocked_for_tradable === false
    && summary.same_sample_selection_blocked_for_tradable === false;
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
    score_proportional_capped: '팩터 점수 비례·상한 적용',
    best_factor_score_proportional_capped: '최고 팩터 점수 비례·상한 적용',
    top_factor_equal_sleeve: '상위 팩터 동일비중 합산',
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

function selectedLookbackMonths() {
  const selector = document.querySelector('#lookback-months-select');
  return Math.round(clampNumber(selector?.value, 1, 60, DASHBOARD_INPUT_DEFAULTS.lookbackMonths));
}

function selectedRebalanceFrequency() {
  const selector = document.querySelector('#rebalance-select');
  const value = selector?.value || DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
  return ['W', 'ME', 'QE'].includes(value) ? value : DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
}

function clampedTransactionCostBps() {
  const input = document.querySelector('#transaction-cost-input');
  const value = clampNumber(input?.value, 0, 200, DASHBOARD_INPUT_DEFAULTS.transactionCostBps);
  if (input && String(input.value) !== String(value)) input.value = String(value);
  return value;
}

function clampedSlippageBps() {
  const input = document.querySelector('#slippage-input');
  const value = clampNumber(input?.value, 0, 200, DASHBOARD_INPUT_DEFAULTS.slippageBps);
  if (input && String(input.value) !== String(value)) input.value = String(value);
  return value;
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
  const input = document.querySelector('#max-weight-input');
  const percent = clampNumber(input?.value, 1, 50, DASHBOARD_INPUT_DEFAULTS.maxWeightPercent);
  if (input && String(input.value) !== String(percent)) input.value = String(percent);
  return percent / 100;
}

function inputScenarioParameters() {
  const transactionCostBps = clampedTransactionCostBps();
  const slippageBps = clampedSlippageBps();
  return {
    lookbackMonths: selectedLookbackMonths(),
    topN: clampedTopN(),
    maxWeight: clampedMaxWeight(),
    rebalanceFrequency: selectedRebalanceFrequency(),
    transactionCostBps,
    slippageBps,
    totalCostRate: (transactionCostBps + slippageBps) / 10000,
  };
}

function rebalanceFrequencyLabel(value) {
  const labels = { W: '주간', ME: '월간', QE: '분기' };
  return labels[value] || value || '-';
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

function factorWeightSnapshot(run, date, windowKey, factor) {
  return (run.factor_weight_snapshots || []).find((snapshot) => (
    snapshot.date === date && snapshot.window === windowKey && snapshot.factor === factor
  )) || null;
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

function normalizeWeightRows(snapshot) {
  const rows = snapshot?.rows || [];
  return rows
    .map((row) => {
      if (Array.isArray(row)) return { symbol: row[0], weight: Number(row[1]), score: Number(row[2]) };
      return { symbol: row.symbol, weight: Number(row.weight ?? row.default_weight), score: Number(row.score) };
    })
    .filter((row) => row.symbol && Number.isFinite(row.weight) && row.weight > 0)
    .sort((a, b) => Number(b.weight) - Number(a.weight) || String(a.symbol).localeCompare(String(b.symbol)));
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

function topFactorsForDate(run, date, windowKey, limit = 10) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    return matrix.factors
      .map((factor, index) => ({
        factor,
        rank: index + 1,
        period_return: optionalNumber(matrix.returns?.[index]),
        window_label: matrix.window_label || windowKey,
        factor_count: matrix.factor_count || matrix.factors.length,
      }))
      .filter((row) => row.factor)
      .slice(0, limit);
  }
  return (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
    .slice(0, limit)
    .map((row, index) => ({
      factor: row.factor,
      rank: row.rank || index + 1,
      period_return: optionalNumber(row.period_return),
      window_label: row.window_label || windowKey,
      factor_count: row.factor_count || null,
    }))
    .filter((row) => row.factor);
}

function capAggregatedWeights(rows, maxWeight) {
  const cap = Math.max(0.01, Math.min(0.5, Number(maxWeight) || 0.1));
  const clean = rows
    .map((row) => ({ ...row, raw_ensemble_weight: Math.max(0, Number(row.raw_ensemble_weight) || 0) }))
    .filter((row) => row.symbol && row.raw_ensemble_weight > 0);
  const rawTotal = clean.reduce((sum, row) => sum + row.raw_ensemble_weight, 0);
  if (!clean.length || rawTotal <= 0) {
    return {
      rows: [],
      investedTotal: 0,
      cashTotal: 1,
      maxWeight: cap,
    };
  }
  const targetBudget = Math.min(1, rawTotal);
  const weights = clean.map((row) => row.raw_ensemble_weight * targetBudget / rawTotal);
  const active = new Set(clean.map((_, index) => index));
  let remainingBudget = targetBudget;
  while (active.size && remainingBudget > 1e-12) {
    const activeWeightTotal = [...active].reduce((sum, index) => sum + weights[index], 0);
    if (activeWeightTotal <= 0) break;
    const cappedThisRound = [];
    for (const index of active) {
      const candidateWeight = remainingBudget * (weights[index] / activeWeightTotal);
      if (candidateWeight > cap) {
        weights[index] = cap;
        cappedThisRound.push(index);
      }
    }
    if (!cappedThisRound.length) {
      for (const index of active) {
        weights[index] = remainingBudget * (weights[index] / activeWeightTotal);
      }
      remainingBudget = 0;
      break;
    }
    cappedThisRound.forEach((index) => {
      active.delete(index);
      remainingBudget -= weights[index];
    });
  }
  const cappedRows = clean.map((row, index) => ({
    ...row,
    display_weight: Math.max(0, weights[index] || 0),
    weight_cap: cap,
    weight_cap_excess: Math.max(0, (row.raw_ensemble_weight * targetBudget / rawTotal) - (weights[index] || 0)),
  }));
  const investedTotal = cappedRows.reduce((sum, row) => sum + row.display_weight, 0);
  return {
    rows: cappedRows,
    investedTotal,
    cashTotal: Math.max(0, 1 - investedTotal),
    maxWeight: cap,
  };
}

function topFactorEnsembleAllocation(run, date, windowKey, topN, maxWeight, factorLimit = 10) {
  const factorRows = topFactorsForDate(run, date, windowKey, factorLimit);
  const displayTopN = Math.max(1, Math.min(50, Math.round(Number(topN) || 20)));
  const sleeves = [];
  const missingFactors = [];
  factorRows.forEach((factorRow) => {
    const snapshot = factorWeightSnapshot(run, date, windowKey, factorRow.factor);
    const rows = normalizeWeightRows(snapshot);
    if (!rows.length) {
      missingFactors.push(factorRow.factor);
      return;
    }
    sleeves.push({ ...factorRow, snapshot, rows });
  });

  const bySymbol = new Map();
  const sleeveWeight = sleeves.length ? 1 / sleeves.length : 0;
  sleeves.forEach((sleeve) => {
    sleeve.rows.forEach((row) => {
      const key = String(row.symbol);
      const current = bySymbol.get(key) || {
        symbol: key,
        raw_ensemble_weight: 0,
        factor_count: 0,
        factors: [],
        score_sum: 0,
        best_score: Number.NEGATIVE_INFINITY,
        factor_weight_sum: 0,
      };
      const sleeveContribution = sleeveWeight * (Number(row.weight) || 0);
      current.raw_ensemble_weight += sleeveContribution;
      current.factor_weight_sum += Number(row.weight) || 0;
      current.factor_count += 1;
      current.factors.push(sleeve.factor);
      current.score_sum += Number(row.score) || 0;
      current.best_score = Math.max(current.best_score, Number(row.score) || Number.NEGATIVE_INFINITY);
      bySymbol.set(key, current);
    });
  });

  const capped = capAggregatedWeights([...bySymbol.values()], maxWeight);
  const allWeighted = capped.rows
    .sort((a, b) => (
      Number(b.display_weight) - Number(a.display_weight)
      || Number(b.factor_count) - Number(a.factor_count)
      || Number(b.score_sum) - Number(a.score_sum)
      || String(a.symbol).localeCompare(String(b.symbol))
    ));
  const weighted = allWeighted
    .slice(0, displayTopN)
    .map((row, index) => ({
      ...row,
      display_rank: index + 1,
      display_weight: Math.max(0, row.display_weight || 0),
      weighting_method: 'top_factor_equal_sleeve',
    }));

  return {
    weighted,
    topN: displayTopN,
    factorRows,
    sleeves,
    factorsUsedCount: sleeves.length,
    factorLimit,
    missingFactors,
    totalCandidateCount: bySymbol.size,
    hiddenWeight: allWeighted.slice(displayTopN).reduce((sum, row) => sum + (Number(row.display_weight) || 0), 0),
    investedTotal: capped.investedTotal,
    cashTotal: capped.cashTotal,
    maxWeight: capped.maxWeight,
    windowLabel: factorRows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
  };
}

function latestOutputFactor(run) {
  const rows = Array.isArray(run.latest_output_rows) ? run.latest_output_rows : [];
  if (!rows.length) return '';
  const rowFactors = [...new Set(rows.map((row) => row?.selected_factor).filter(Boolean))];
  if (rowFactors.length === 1) return rowFactors[0];
  if (rowFactors.length === 0) return run.summary?.selected_factor || '';
  return '';
}

function latestOutputMatchesFactor(run, factor) {
  const outputFactor = latestOutputFactor(run);
  return Boolean(outputFactor && factor && outputFactor === factor);
}

function latestOutputSignalRows(run, topN, factor = null) {
  if (factor && !latestOutputMatchesFactor(run, factor)) return [];
  const rows = Array.isArray(run.latest_output_rows) ? run.latest_output_rows : [];
  const count = Math.max(1, Math.min(50, Math.round(Number(topN) || 20), rows.length || 1));
  return rows.slice(0, count).map((row, index) => ({
    rank: row.rank || index + 1,
    symbol: row.symbol,
    score: optionalNumber(row.score),
    weight: optionalNumber(row.weight) || 0,
    pre_cap_weight: optionalNumber(row.pre_cap_weight ?? row.proposed_weight ?? row.weight) || 0,
    weighting_method: row.weighting_method || 'latest_output_rows',
    signal_date: row.signal_date || run.summary?.data_as_of || '-',
    selected_factor: row.selected_factor || run.summary?.selected_factor || '-',
  })).filter((row) => row.symbol);
}

function bestFactorSignalRows(run, date, windowKey, topN, maxWeight) {
  const best = periodBestStats(run, date, windowKey);
  const snapshot = best?.factor ? factorScoreSnapshot(run, date, best.factor) : null;
  const allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  const researchOnly = !isPracticalRun(run);
  const requestedTopN = Math.max(1, Math.min(50, Math.round(Number(topN) || 20)));
  let rows = allocation.weighted.map((row) => ({
    rank: row.display_rank,
    symbol: row.symbol,
    score: row.score,
    weight: researchOnly ? 0 : row.display_weight,
    pre_cap_weight: row.display_weight,
    weighting_method: 'best_factor_score_proportional_capped',
    signal_date: snapshot?.score_date || date,
    selected_factor: best?.factor || '-',
  }));
  let signalSource = 'best_factor_score_snapshot';
  if (!rows.length && Array.isArray(run.latest_output_rows) && run.latest_output_rows.length) {
    rows = latestOutputSignalRows(run, requestedTopN);
    signalSource = 'latest_output_rows_fallback';
  }
  return {
    rows,
    best,
    snapshot,
    allocation,
    researchOnly,
    signalSource,
    topN: signalSource === 'latest_output_rows_fallback' ? requestedTopN : allocation.topN,
    maxWeight: allocation.maxWeight,
    windowLabel: best?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
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

function humanSourceName(value) {
  const text = textValue(value);
  const labels = {
    'yfinance-adjusted-daily': 'yfinance 조정가격',
    'yahoo-chart-adjusted-daily-fallback': 'Yahoo chart 보강',
    'nasdaq-latest-close-repair': 'Nasdaq 최신일 보강',
    'stooq-daily-close-fallback': 'Stooq 대체',
    'finance-datareader-close-fallback': 'FinanceDataReader 대체',
    'yfinance-fast-info-market-cap': '시가총액 보강',
    'finviz-snapshot-market-cap': 'Finviz 시가총액 보강',
    'live-run-summary': '전체 실행 요약',
    'packaged-default-universe': '패키지 유니버스',
  };
  return labels[text] || text;
}

function formatCoverageMetric(ratio, numerator, denominator) {
  const ratioText = formatPercent(ratio);
  const num = Number(numerator);
  const den = Number(denominator);
  if (Number.isFinite(num) && Number.isFinite(den) && den > 0) {
    return `${ratioText} (${formatInteger(num)} / ${formatInteger(den)})`;
  }
  return ratioText;
}

function formatSourceHealth(rows) {
  if (!Array.isArray(rows) || !rows.length) return '-';
  return rows
    .filter((row) => row && row.source)
    .slice(0, 8)
    .map((row) => {
      const parts = [];
      if (Number(row.success_rows) > 0) parts.push(`성공 ${formatInteger(row.success_rows)}`);
      if (Number(row.no_newer_rows) > 0) parts.push(`추가 없음 ${formatInteger(row.no_newer_rows)}`);
      if (Number(row.failed_rows) > 0) parts.push(`실패 ${formatInteger(row.failed_rows)}`);
      if (!parts.length) parts.push(`행 ${formatInteger(row.row_count)}`);
      return `${humanSourceName(row.source)}: ${parts.join(', ')}`;
    })
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

function appendHeader(tr, value) {
  const th = document.createElement('th');
  th.textContent = textValue(value);
  tr.appendChild(th);
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

function scenarioAllocationForFactor(run, date, windowKey, factor, topN, maxWeight) {
  const snapshot = factorScoreSnapshot(run, date, factor);
  let allocation = computeScenarioAllocation(snapshot?.rows || [], topN, maxWeight);
  let fallbackSource = null;
  if (!allocation.weighted.length) {
    const weightSnapshot = factorWeightSnapshot(run, date, windowKey, factor);
    const weightRows = normalizeWeightRows(weightSnapshot).map((row) => ({
      symbol: row.symbol,
      score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.weight) || 0,
    }));
    allocation = computeScenarioAllocation(weightRows, topN, maxWeight);
    if (allocation.weighted.length) fallbackSource = 'factor_weight_snapshot_fallback';
  }
  if (!allocation.weighted.length) {
    const holdingRows = (run.holdings || [])
      .filter((row) => row.date === date && row.window === windowKey && row.factor === factor)
      .map((row) => ({
        symbol: row.symbol,
        score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.default_weight) || 0,
      }));
    allocation = computeScenarioAllocation(holdingRows, topN, maxWeight);
    if (allocation.weighted.length) fallbackSource = 'holding_rows_fallback';
  }
  const latestOutputRowsFactor = latestOutputFactor(run);
  if (
    !allocation.weighted.length
    && Array.isArray(run.latest_output_rows)
    && run.latest_output_rows.length
    && latestOutputMatchesFactor(run, factor)
  ) {
    const fallbackRows = latestOutputSignalRows(run, topN, factor).map((row, index) => {
      const displayWeight = Math.max(0, Math.min(maxWeight, optionalNumber(row.pre_cap_weight) || optionalNumber(row.weight) || 0));
      return {
        ...row,
        display_rank: row.rank || index + 1,
        display_weight: displayWeight,
        scenario_weight: displayWeight,
      };
    });
    const investedTotal = fallbackRows.reduce((sum, row) => sum + (Number(row.display_weight) || 0), 0);
    allocation = {
      weighted: fallbackRows,
      investedTotal,
      displayedTotal: investedTotal,
      portfolioTotal: investedTotal,
      cashTotal: Math.max(0, 1 - investedTotal),
      unusedCandidateCount: Math.max(0, (run.latest_output_rows || []).length - fallbackRows.length),
      weightingMethod: 'latest_output_rows_fallback',
      topN: Math.max(1, Math.min(50, Math.round(Number(topN) || DASHBOARD_INPUT_DEFAULTS.topN))),
      maxWeight,
      availableCount: fallbackRows.length,
    };
    fallbackSource = 'latest_output_rows_fallback';
  }
  return { allocation, snapshot, fallbackSource, latestOutputRowsFactor };
}

function currentWeightedHoldings() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const { allocation, snapshot, fallbackSource, latestOutputRowsFactor } = scenarioAllocationForFactor(run, date, windowKey, factor, topN, maxWeight);
  const availableDates = factorAvailableDates(run, factor);
  const stats = periodFactorStats(run, date, windowKey, factor);
  return {
    ...allocation,
    snapshot,
    selectedFactor: factor || '-',
    windowLabel: stats?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || windowKey || '-',
    scoreDate: snapshot?.score_date || (fallbackSource ? run.summary?.data_as_of || null : null),
    scoreScope: snapshot?.score_scope || fallbackSource,
    latestOutputRowsFactor,
    rawAvailableCount: snapshot?.raw_available_count ?? null,
    eligibilityFilterApplied: snapshot?.eligibility_filter_applied === true,
    missingReason: snapshot
      ? null
      : fallbackSource
      ? null
      : latestOutputRowsFactor && factor && latestOutputRowsFactor !== factor
      ? `저장된 latest_output_rows는 ${latestOutputRowsFactor} 기준이라 선택 팩터 ${factor} 시나리오로 표시하지 않습니다.`
      : availableDates.size && !availableDates.has(date)
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
  const hasFactorSpecificDates = Object.keys(byFactor).length > 0;
  const dates = [...(hasFactorSpecificDates ? (byFactor[factor] || []) : (run.scenario_available_dates || []))];
  if (!dates.length && latestOutputMatchesFactor(run, factor) && run.summary?.data_as_of) {
    dates.push(run.summary.data_as_of);
  }
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

function factorOptionLabel(item, bestDefaultFactor, run) {
  if (item.factor === bestDefaultFactor) return `${item.factor} · 현재 기준 최고 팩터`;
  if (item.factor === run.summary?.selected_factor) return `${item.factor} · 실행 저장 선택`;
  return `${item.factor} · ${humanFactorCategory(item.category)}`;
}

function updateFactorOptionLabels(run, bestDefaultFactor) {
  const factorSelect = document.querySelector('#factor-select');
  if (!factorSelect) return;
  const metadata = new Map(factorOptions(run).map((item) => [item.factor, item]));
  Array.from(factorSelect.children || []).forEach((option) => {
    const item = metadata.get(option.value) || { factor: option.value, category: 'unknown' };
    option.textContent = factorOptionLabel(item, bestDefaultFactor, run);
  });
}

function syncDefaultFactorToCurrentBasis() {
  if (state.hasUserSelectedFactor) return;
  const run = currentRun();
  const factorSelect = document.querySelector('#factor-select');
  if (!run || !factorSelect) return;
  const bestDefaultFactor = periodBestStats(run, selectedDate(), selectedWindow())?.factor;
  updateFactorOptionLabels(run, bestDefaultFactor);
  const values = Array.from(factorSelect.children || []).map((option) => option.value);
  if (bestDefaultFactor && values.includes(bestDefaultFactor)) {
    factorSelect.value = bestDefaultFactor;
    fillDateOptions(run, selectedDate());
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
  const windows = run.periods || [];
  const windowSelect = document.querySelector('#window-select');
  const previousWindow = windowSelect?.value || '';
  windowSelect.replaceChildren();
  windows.forEach((period) => {
    const option = document.createElement('option');
    option.value = period.key;
    option.textContent = period.label;
    windowSelect.appendChild(option);
  });
  const windowKeys = windows.map((period) => period.key);
  const defaultWindow = windowKeys.includes(DASHBOARD_INPUT_DEFAULTS.window)
    ? DASHBOARD_INPUT_DEFAULTS.window
    : (windowKeys.includes('1Y') ? '1Y' : (windowKeys.at(-1) || windowKeys[0] || '1M'));
  windowSelect.value = windowKeys.includes(previousWindow) ? previousWindow : defaultWindow;

  const previousDate = document.querySelector('#date-select')?.value || null;
  fillDateOptions(run, previousDate);
  const dateForDefault = selectedDate();

  const factorSelect = document.querySelector('#factor-select');
  const previousFactor = state.hasUserSelectedFactor ? factorSelect?.value || '' : '';
  factorSelect.replaceChildren();
  const options = factorOptions(run);
  const bestDefaultFactor = periodBestStats(run, dateForDefault, windowSelect.value)?.factor;
  options.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.factor;
    option.textContent = factorOptionLabel(item, bestDefaultFactor, run);
    factorSelect.appendChild(option);
  });
  const factors = options.map((item) => item.factor);
  factorSelect.value = previousFactor && factors.includes(previousFactor)
    ? previousFactor
    : (factors.includes(bestDefaultFactor) ? bestDefaultFactor : (factors.includes(run.summary?.selected_factor) ? run.summary.selected_factor : factors[0] || ''));

  fillDateOptions(run, selectedDate());
  document.querySelector('#topn-input').value = DASHBOARD_INPUT_DEFAULTS.topN;
  document.querySelector('#max-weight-input').value = DASHBOARD_INPUT_DEFAULTS.maxWeightPercent;
  const lookback = document.querySelector('#lookback-months-select');
  if (lookback) lookback.value = String(DASHBOARD_INPUT_DEFAULTS.lookbackMonths);
  const rebalance = document.querySelector('#rebalance-select');
  if (rebalance) rebalance.value = DASHBOARD_INPUT_DEFAULTS.rebalanceFrequency;
  const transactionCost = document.querySelector('#transaction-cost-input');
  if (transactionCost) transactionCost.value = String(DASHBOARD_INPUT_DEFAULTS.transactionCostBps);
  const slippage = document.querySelector('#slippage-input');
  if (slippage) slippage.value = String(DASHBOARD_INPUT_DEFAULTS.slippageBps);
}

function renderSummary() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const params = inputScenarioParameters();
  const scenarioRows = scenarioPeriodRows(run, date, windowKey, params);
  const best = scenarioRows[0] || scenarioBestStats(run, date, windowKey, params);
  const factor = selectedFactor();
  const selectedStats = scenarioRows.find((row) => row.factor === factor) || scenarioFactorStats(run, date, windowKey, factor, params);
  const summary = run.summary || {};
  const latestRunAt = formatKoreanDateTime(summary.run_timestamp_utc);
  const runPayloadGeneratedAtText = formatKoreanDateTime(runPayloadGeneratedAt(run));
  setText('#best-factor', best?.factor || '-');
  setText(
    '#best-factor-detail',
    best
      ? `${best.window_label} 브라우저 시나리오 수익률 ${formatPercent(best.period_return)}${best.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(best.raw_period_return)}` : ''}`
      : '-',
  );
  setText('#selected-factor', factor || '-');
  setText(
    '#selected-factor-detail',
    selectedStats && selectedStats.rank
      ? `${selectedStats.window_label} 브라우저 시나리오 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'} · ${formatPercent(selectedStats.period_return)}${selectedStats.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(selectedStats.raw_period_return)}` : ''} · ${factorDescription(factor, run)}`
      : `자료 없음 · ${factorDescription(factor, run)}`,
  );
  setText('#recommendation-status', humanStatus(summary.recommendation_status, summary.recommendation_output_label));
  setText('#data-provider', `기준일 ${summary.data_as_of || '-'} · ${humanProvider(summary.provider)}`);
  setText('#latest-run-at', latestRunAt);
  setText('#latest-run-detail', `분석 실행 기준 · 실행 결과 생성 ${runPayloadGeneratedAtText}`);
  const scenario = currentWeightedHoldings();
  setText(
    '#scenario-live-summary',
    `브라우저 시나리오/프록시 입력 · 최근 ${params.lookbackMonths}개월 · 상위 ${params.topN}개 · 종목당 최대 ${formatPercent(params.maxWeight)} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 리밸런싱 · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps · 시나리오 투자 ${formatPercent(scenario.investedTotal)} · 현금/미사용 ${formatPercent(scenario.cashTotal)}`,
  );

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
  appendDefinition(dataSummary, '모형 가격 보유 종목', formatCount(quality.fetched_price_symbol_count));
  appendDefinition(dataSummary, '제외 종목 수', formatCount(quality.excluded_symbols));
  appendDefinition(
    dataSummary,
    '요청 가격 커버리지',
    formatCoverageMetric(
      quality.price_coverage_ratio,
      quality.provider_returned_symbol_count,
      quality.provider_requested_symbol_count,
    ),
  );
  appendDefinition(
    dataSummary,
    '모형 가격 보유 비율',
    formatCoverageMetric(
      quality.model_price_universe_ratio,
      quality.fetched_price_symbol_count,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '가격 적격 비율',
    formatCoverageMetric(
      quality.eligible_price_ratio,
      summary.eligible_price_universe_size ?? quality.eligible_price_universe_size,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '유동성 적격 비율',
    formatCoverageMetric(
      quality.liquidity_eligible_ratio,
      summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size,
      summary.candidate_universe_size ?? quality.candidate_universe_size,
    ),
  );
  appendDefinition(
    dataSummary,
    '신선 가격 비율',
    formatCoverageMetric(quality.fresh_price_ratio, quality.fresh_price_rows, quality.price_quality_rows),
  );
  appendDefinition(dataSummary, '데이터 기준일', quality.data_as_of || summary.data_as_of || '-');
  appendDefinition(dataSummary, '최근 실행 시각', formatKoreanDateTime(summary.run_timestamp_utc));
  appendDefinition(dataSummary, '실행 결과 생성 시각', formatKoreanDateTime(runPayloadGeneratedAt(run)));
  appendDefinition(dataSummary, '가격 제공자', humanProvider(quality.provider || summary.provider));
  appendDefinition(dataSummary, '소스별 수집 상태', formatSourceHealth(quality.source_health));
  appendDefinition(
    dataSummary,
    '가격 소스 분포',
    formatCounts(quality.price_source_counts, {
      'yfinance-adjusted-daily': 'yfinance',
      'yahoo-chart-adjusted-daily-fallback': 'Yahoo chart',
      'nasdaq-latest-close-repair': 'Nasdaq 보강',
      'stooq-daily-close-fallback': 'Stooq',
      'finance-datareader-close-fallback': 'FinanceDataReader',
    }),
  );
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
  const params = inputScenarioParameters();
  const rows = (run.factor_leaders || []).filter((row) => row.window === windowKey).slice(-30).reverse();
  const tbody = document.querySelector('#factor-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const scenarioRows = scenarioPeriodRows(run, row.date, row.window, params);
    const bestStats = scenarioRows[0] || periodBestStats(run, row.date, row.window);
    const selectedStats = scenarioRows.find((item) => item.factor === factor) || scenarioFactorStats(run, row.date, row.window, factor, params);
    const tr = document.createElement('tr');
    appendCell(tr, row.date);
    appendCell(tr, row.window_label, { badge: true });
    appendCell(tr, bestStats?.factor || row.best_factor);
    appendCell(tr, bestStats?.period_return == null ? '자료 없음' : `${formatPercent(bestStats.period_return)} · 시나리오`, { className: classForNumber(bestStats?.period_return) });
    appendCell(tr, selectedStats?.period_return == null ? '자료 없음' : `${formatPercent(selectedStats.period_return)} · 시나리오`, { className: classForNumber(selectedStats?.period_return) });
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
    scoreScope,
    unusedCandidateCount,
    maxWeight,
    rawAvailableCount,
    eligibilityFilterApplied,
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
  const usingLatestOutputFallback = scoreScope === 'latest_output_rows_fallback';
  const scopeNote = usingLatestOutputFallback
    ? `점수 스냅샷이 없어 저장된 latest_output_rows ${formatInteger(availableCount)}개를 선택 팩터 시나리오 fallback으로 표시합니다.`
    : eligibilityFilterApplied
    ? `현재 모델 편입 가능 필터를 통과한 ${formatInteger(availableCount)}개 후보를 사용합니다${rawAvailableCount && rawAvailableCount !== availableCount ? ` (원점수 후보 ${formatInteger(rawAvailableCount)}개 중 실무 필터 통과분)` : ''}.`
    : `편입 가능 필터 정보가 없어 원점수 후보 ${formatInteger(availableCount)}개를 연구 진단용으로 표시합니다.`;
  setText(
    '#holdings-availability',
    missingReason
      ? `${missingReason} 기간 최고 팩터 보유를 대신 보여주지 않습니다.`
      : run.history_payload_type === 'summary'
      ? '이전 실행은 페이지 속도를 위해 요약 이력만 보관합니다. 상위 종목과 비중은 최신 실행에서 전체 표시됩니다.'
      : usingLatestOutputFallback
      ? `${windowLabel} 선택 팩터 ${factor}의 점수 스냅샷이 없어 기존 최신 출력 행 기준입니다. ${scopeNote} 상위 ${Math.min(topN, availableCount)}개를 표시하며, 저장된 게이트 전 비중을 종목당 최대 ${formatPercent(maxWeight)}로 제한해 표시합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`
      : `${windowLabel} 선택 팩터 ${factor}의 ${scoreDate || '최근'} 점수 스냅샷 기준입니다. ${scopeNote} 상위 ${Math.min(topN, availableCount)}개를 표시하며, ${weightLabel}은 브라우저가 팩터 점수 비례 배분과 종목당 최대 ${formatPercent(maxWeight)} 가정으로 계산합니다. 미선택 후보 ${formatInteger(unusedCandidateCount)}개 · ${capNote}`,
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
  const summary = run.summary || {};
  const quality = run.data_quality_summary || {};
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const {
    rows,
    best,
    snapshot,
    allocation,
    researchOnly,
    signalSource,
    windowLabel,
  } = bestFactorSignalRows(run, date, windowKey, topN, maxWeight);
  const tbody = document.querySelector('#current-output-table tbody');
  const note = document.querySelector('#current-output-note');
  tbody.replaceChildren();
  if (note) {
    const blockers = joinReasonList(summary.tradability_blockers) || joinReasonList(summary.fail_closed_reasons) || '실전 매매 게이트 미통과';
    const candidateCount = formatCount(summary.candidate_universe_size ?? quality.candidate_universe_size);
    const eligibleCount = formatCount(summary.eligible_price_universe_size ?? quality.eligible_price_universe_size);
    const liquidityCount = formatCount(summary.liquidity_eligible_universe_size ?? quality.liquidity_eligible_universe_size);
    const usingLatestOutputFallback = signalSource === 'latest_output_rows_fallback';
    const scope = usingLatestOutputFallback
      ? `${run.summary?.data_as_of || date || '-'} · 기존 최신 출력 행`
      : best?.factor
      ? `${date || '-'} · ${windowLabel} 최고 팩터 ${best.factor}`
      : `${date || '-'} · ${windowLabel} 최고 팩터 자료 없음`;
    const availability = usingLatestOutputFallback
      ? `최고 팩터 점수 스냅샷이 없어 저장된 latest_output_rows ${formatInteger(rows.length)}개를 투명한 fallback으로 표시합니다.`
      : snapshot
      ? `모델 편입 가능 후보 ${formatInteger(allocation.availableCount)}개 중 상위 ${rows.length}개를 표시합니다.`
      : '해당 최고 팩터의 종목 점수 스냅샷이 없어 행을 표시하지 못했습니다.';
    const bestFactorCaution = 'Best factor는 해당 기간의 과거 성과 1위 팩터이므로 미래 우위를 보장하지 않으며, 선택 팩터 드롭다운과 별개입니다.';
    note.textContent = researchOnly
      ? `${scope} · 연구용 신호(매매 비중 0%). ${availability} ${bestFactorCaution} 미충족: ${blockers}. 후보 ${candidateCount} · 가격 적격 ${eligibleCount} · 유동성 적격 ${liquidityCount}.`
      : `${scope} 기준 표시용 best-factor 신호입니다. ${availability} ${bestFactorCaution} 후보 ${candidateCount}, 가격 적격 ${eligibleCount}, 유동성 적격 ${liquidityCount}.`;
  }
  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.textContent = '선택한 기준일과 기간의 최고 팩터에 표시할 신호 스냅샷이 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  rows.forEach((row, index) => {
    const tr = document.createElement('tr');
    appendCell(tr, row.rank || index + 1);
    appendCell(tr, row.symbol, { strong: true });
    appendCell(tr, formatNumber(row.score));
    appendCell(tr, row.selected_factor || best?.factor || '-');
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
  const params = inputScenarioParameters();
  let rows = scenarioPeriodRows(run, date, windowKey, params);
  const best = rows[0] || scenarioBestStats(run, date, windowKey, params);
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 10);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const target = document.querySelector('#factor-return-chart');
  target.replaceChildren();
  const windowLabel = rows[0]?.window_label || (run.periods || []).find((period) => period.key === windowKey)?.label || '-';
  setText(
    '#factor-chart-meta',
    `${date || '-'} · ${windowLabel} · 브라우저 시나리오/프록시 · 최근 ${params.lookbackMonths}개월 · 선택 ${factor || '-'} · 상위 ${params.topN}개 · 최대 ${formatPercent(params.maxWeight)} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps`,
  );
  if (!rows.length) {
    appendEmpty('#factor-return-chart', '선택한 기준일과 기간에 표시할 팩터 수익률 데이터가 없습니다.');
    return;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.period_return) || 0)), 0.01);
  rows.forEach((row) => appendBarRow(
    target,
    `${row.rank}. ${row.factor}`,
    `${formatPercent(row.period_return)}${row.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(row.raw_period_return)}` : ''}`,
    row.period_return,
    maxAbs,
    { className: `${row.factor === factor ? 'is-selected' : ''} ${row.factor === best?.factor ? 'is-best' : ''}`.trim() },
  ));
  const note = document.createElement('div');
  note.className = 'scenario-note';
  const fallbackCount = rows.filter((row) => !row.scenario_adjusted).length;
  note.textContent = `막대값은 저장된 팩터 누적성과를 현재 입력값의 비중 집중도·리밸런싱·거래비용 가정으로 조정한 브라우저 시나리오/민감도 프록시입니다.${fallbackCount ? ` ${fallbackCount}개 팩터는 필요한 백테스트 시계열이 부족해 원자료 수익률 fallback을 사용했습니다.` : ''}`;
  target.appendChild(note);
  if (!selectedRow) {
    const missingNote = document.createElement('div');
    missingNote.className = 'scenario-note';
    missingNote.textContent = '선택 팩터가 이 기준일/기간의 내보낸 순위 데이터에 없습니다. 팩터 비교는 가능한 데이터 범위 안에서만 표시됩니다.';
    target.appendChild(missingNote);
  }
}

function renderWindowComparisonChart() {
  const run = currentRun();
  const date = selectedDate();
  const selectedFactorName = selectedFactor();
  const params = inputScenarioParameters();
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
    const scenarioRows = scenarioPeriodRows(run, row.date, row.window, params);
    const best = scenarioRows[0] || periodBestStats(run, row.date, row.window);
    const selectedStats = scenarioRows.find((item) => item.factor === selectedFactorName) || scenarioFactorStats(run, row.date, row.window, selectedFactorName, params);
    const factorNode = document.createElement('strong');
    factorNode.textContent = best?.factor || row.best_factor || '-';
    const detail = document.createElement('small');
    detail.textContent = selectedStats?.rank
      ? `브라우저 시나리오 최고 ${formatPercent(best?.period_return)} · 선택 팩터 ${formatPercent(selectedStats.period_return)} · 순위 ${selectedStats.rank}/${selectedStats.factor_count || '-'}`
      : `브라우저 시나리오 최고 ${formatPercent(best?.period_return)} · 선택 팩터 자료 없음`;
    chip.append(label, factorNode, detail);
    target.appendChild(chip);
  });
}

function renderLeaderTrendChart() {
  const run = currentRun();
  const windowKey = selectedWindow();
  const params = inputScenarioParameters();
  const rows = (run.factor_leaders || [])
    .filter((row) => row.window === windowKey)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .slice(-30)
    .map((row) => {
      const best = scenarioBestStats(run, row.date, row.window, params);
      return {
        ...row,
        best_factor: best?.factor || row.best_factor,
        best_return: best?.period_return ?? row.best_return,
        scenario_adjusted: best?.scenario_adjusted === true,
      };
    });
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
    bar.title = `${row.date} · ${row.best_factor} · ${formatPercent(row.best_return)} · 브라우저 시나리오/프록시`;
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
  setText('#weight-chart-meta', `${isPracticalRun(run) ? '투자 시나리오' : '연구 시나리오'} · 선택 팩터 ${selectedFactor() || '-'} · 상위 ${topN}개 · 최대 ${formatPercent(maxWeight)}`);
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

function renderEnsembleWeightChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const topN = clampedTopN();
  const maxWeight = clampedMaxWeight();
  const target = document.querySelector('#ensemble-weight-chart');
  target.replaceChildren();
  const ensemble = topFactorEnsembleAllocation(run, date, windowKey, topN, maxWeight, 10);
  setText(
    '#ensemble-chart-meta',
    `${date || '-'} · ${ensemble.windowLabel} · ${ensemble.factorsUsedCount}/${Math.min(10, ensemble.factorRows.length)}개 팩터 · 최종 상한 ${formatPercent(ensemble.maxWeight)}`,
  );
  if (!ensemble.weighted.length) {
    appendEmpty(
      '#ensemble-weight-chart',
      '선택한 기준일과 기간에 상위 팩터의 백테스트 보유 비중 스냅샷이 없어 합산 비중을 표시할 수 없습니다.',
    );
    return;
  }
  const maxWeightValue = Math.max(
    ...ensemble.weighted.map((row) => Number(row.display_weight) || 0),
    0.01,
  );
  ensemble.weighted.forEach((row) => {
    const label = `${row.symbol} · ${row.factor_count}개 팩터`;
    appendBarRow(target, label, formatPercent(row.display_weight), row.display_weight, maxWeightValue);
  });
  const factorNames = ensemble.sleeves.map((sleeve) => `${sleeve.rank}. ${sleeve.factor}`).join(', ');
  const note = document.createElement('div');
  note.className = 'scenario-note';
  const missing = ensemble.missingFactors.length
    ? ` 스냅샷이 없는 팩터 ${ensemble.missingFactors.length}개는 제외했습니다.`
    : '';
  note.textContent = `해석: ${ensemble.windowLabel} 성과 상위 팩터들을 각각 같은 팩터별 포트폴리오 비중으로 보고, 각 팩터 내부는 기존 백테스트 일별 보유 비중을 그대로 사용한 뒤 중복 종목 비중을 합산했습니다. 합산 후 브라우저 종목당 최대 비중 ${formatPercent(ensemble.maxWeight)}를 최종 상한으로 적용했습니다. 시각화는 개별 종목 ${ensemble.weighted.length}개만 표시하고, 미표시 후보 합계 ${formatPercent(ensemble.hiddenWeight)} 및 현금/상한 미사용 ${formatPercent(ensemble.cashTotal)}는 숫자로만 제공합니다. 전체 합산 후보 ${ensemble.totalCandidateCount}개. 사용 팩터: ${factorNames}.${missing}`;
  target.appendChild(note);
}

function factorBacktestSeries(run, factor) {
  return (run.factor_backtest_series || []).find((series) => series.factor === factor) || null;
}

function benchmarkBacktestSeries(run) {
  const series = run.benchmark_backtest_series;
  if (!series || !Array.isArray(series.dates)) return null;
  return series;
}

function seriesPointsThroughDate(series, date, limit = 260) {
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

function formatAxisDate(value) {
  if (!value) return '-';
  const parts = String(value).split('-');
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
  return String(value);
}

function formatChartAxisDate(value, mode = 'month') {
  if (!value) return '-';
  const parts = String(value).split('-').map((part) => Number(part));
  if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return formatAxisDate(value);
  const [year, month, day] = parts;
  if (mode === 'quarter') return `${String(year).slice(2)}년 ${Math.floor((month - 1) / 3) + 1}분기`;
  if (mode === 'week') return `${month}/${day}`;
  return `${String(year).slice(2)}.${String(month).padStart(2, '0')}`;
}

function parseDateString(value) {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function daysBetween(start, end) {
  const startDate = parseDateString(start);
  const endDate = parseDateString(end);
  if (!startDate || !endDate) return 0;
  return Math.max(0, Math.round((endDate - startDate) / 86400000));
}

function dateTickKey(year, month, day, mode) {
  if (mode === 'week') return `${year}-${String(month).padStart(2, '0')}-W${Math.ceil(day / 7)}`;
  if (mode === 'quarter') return `${year}-Q${Math.floor((month - 1) / 3) + 1}`;
  return `${year}-${String(month).padStart(2, '0')}`;
}

function dateTickMarks(dates) {
  if (!dates.length) return [];
  const spanDays = daysBetween(dates[0], dates.at(-1));
  const mode = spanDays <= 70 ? 'week' : (spanDays <= 420 ? 'month' : 'quarter');
  const ticks = [];
  let previousKey = '';
  dates.forEach((date, index) => {
    const parts = String(date).split('-').map((part) => Number(part));
    if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return;
    const [year, month, day] = parts;
    const key = dateTickKey(year, month, day, mode);
    if (index === 0 || index === dates.length - 1 || key !== previousKey) {
      if (mode !== 'quarter' || index === 0 || index === dates.length - 1 || [1, 4, 7, 10].includes(month)) {
        ticks.push({ index, date, label: formatChartAxisDate(date, mode) });
      }
    }
    previousKey = key;
  });
  const maxTicks = 12;
  if (ticks.length <= maxTicks) return ticks;
  const stride = Math.ceil((ticks.length - 2) / (maxTicks - 2));
  return ticks.filter((tick, index) => index === 0 || index === ticks.length - 1 || index % stride === 0);
}

function formatPercentTick(value) {
  if (!Number.isFinite(Number(value))) return '-';
  const percent = Number(value) * 100;
  const decimals = Math.abs(percent) < 10 && Math.abs(percent % 1) > 0.001 ? 1 : 0;
  return `${percent.toFixed(decimals)}%`;
}

function niceReturnTicks(minReturn, maxReturn) {
  let lower = Math.min(Number(minReturn) || 0, 0);
  let upper = Math.max(Number(maxReturn) || 0, 0);
  if (Math.abs(upper - lower) < 0.02) {
    lower -= 0.02;
    upper += 0.02;
  }
  const candidates = [0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.0, 2.0, 5.0];
  let step = candidates.at(-1);
  for (const candidate of candidates) {
    const start = Math.floor(lower / candidate) * candidate;
    const end = Math.ceil(upper / candidate) * candidate;
    const count = Math.round((end - start) / candidate) + 1;
    if (count >= 4 && count <= 7) {
      step = candidate;
      break;
    }
  }
  const start = Math.floor(lower / step) * step;
  const end = Math.ceil(upper / step) * step;
  const ticks = [];
  for (let value = start; value <= end + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

const PERFORMANCE_PERIODS = [
  { key: '1W', label: '최근 1주', tradingDays: 5 },
  { key: '1M', label: '최근 1개월', tradingDays: 21 },
  { key: '3M', label: '최근 3개월', tradingDays: 63 },
  { key: '6M', label: '최근 6개월', tradingDays: 126 },
  { key: '1Y', label: '최근 1년', tradingDays: 252 },
  { key: 'YTD', label: 'YTD', ytd: true },
];

const PERFORMANCE_METRICS = [
  { key: 'cumulativeReturn', label: '누적 수익률', formatter: formatPercent },
  { key: 'sharpe', label: '샤프지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'volatility', label: '변동성(표준편차)', formatter: formatPercent },
  { key: 'maxDrawdown', label: 'MDD', formatter: formatPercent },
  { key: 'sortino', label: '소르티노 지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'calmar', label: '칼마 지수', formatter: (value) => formatNumberWithDigits(value, 2) },
  { key: 'cvar', label: 'CVaR(95%)', formatter: formatPercent },
  { key: 'winRate', label: '일간 승률', formatter: formatPercent },
];

function formatNumberWithDigits(value, digits = 2) {
  if (value === Infinity) return '∞';
  if (value === -Infinity) return '-∞';
  if (value === null || value === undefined || Number.isNaN(Number(value)) || !Number.isFinite(Number(value))) return '-';
  return Number(value).toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function periodPoints(points, period) {
  if (!points.length) return [];
  if (period.ytd) {
    const endYear = String(points.at(-1).date || '').slice(0, 4);
    const ytdPoints = points.filter((point) => String(point.date || '').startsWith(endYear));
    return ytdPoints.length >= 2 ? ytdPoints : points.slice(-Math.min(points.length, 2));
  }
  return points.slice(-Math.min(points.length, period.tradingDays + 1));
}

function returnSeries(points) {
  const returns = [];
  for (let index = 1; index < points.length; index += 1) {
    const previous = Number(points[index - 1].equity);
    const current = Number(points[index].equity);
    if (Number.isFinite(previous) && Number.isFinite(current) && previous > 0) {
      returns.push(current / previous - 1);
    }
  }
  return returns;
}

function populationStd(values) {
  if (values.length < 2) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(Math.max(0, variance));
}

function maxDrawdownFromPoints(points) {
  let peak = -Infinity;
  let maxDrawdown = 0;
  points.forEach((point) => {
    const equity = Number(point.equity);
    if (!Number.isFinite(equity)) return;
    peak = Math.max(peak, equity);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, equity / peak - 1);
  });
  return maxDrawdown;
}

function cvarFromReturns(returns, tail = 0.05) {
  const clean = returns.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!clean.length) return null;
  const count = Math.max(1, Math.ceil(clean.length * tail));
  const tailReturns = clean.slice(0, count);
  return tailReturns.reduce((sum, value) => sum + value, 0) / tailReturns.length;
}

function performanceMetrics(points, period) {
  const slice = periodPoints(points, period);
  if (slice.length < 2) return null;
  const returns = returnSeries(slice);
  if (!returns.length) return null;
  const first = Number(slice[0].equity);
  const last = Number(slice.at(-1).equity);
  const cumulativeReturn = first > 0 ? last / first - 1 : null;
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const std = populationStd(returns);
  const downside = returns.filter((value) => value < 0);
  const downsideStd = downside.length >= 2 ? populationStd(downside) : null;
  const annualizedReturn = cumulativeReturn === null || cumulativeReturn <= -1
    ? null
    : ((1 + cumulativeReturn) ** (252 / returns.length) - 1);
  const volatility = std === null ? null : std * Math.sqrt(252);
  const maxDrawdown = maxDrawdownFromPoints(slice);
  const winRate = returns.filter((value) => value > 0).length / returns.length;
  return {
    cumulativeReturn,
    sharpe: std && std > 0 ? (mean / std) * Math.sqrt(252) : null,
    volatility,
    maxDrawdown,
    sortino: downside.length === 0 && mean > 0 ? Infinity : (downsideStd && downsideStd > 0 ? (mean / downsideStd) * Math.sqrt(252) : null),
    calmar: maxDrawdown < 0 && annualizedReturn !== null ? annualizedReturn / Math.abs(maxDrawdown) : null,
    cvar: cvarFromReturns(returns),
    winRate,
  };
}

function appendSvgText(svg, text, x, y, className, anchor = 'middle') {
  const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  label.textContent = text;
  label.setAttribute('x', String(x));
  label.setAttribute('y', String(y));
  label.setAttribute('class', className);
  label.setAttribute('text-anchor', anchor);
  svg.appendChild(label);
  return label;
}

function lookbackFilteredPoints(points, months) {
  if (!points.length) return [];
  const endDate = parseDateString(points.at(-1).date);
  if (!endDate) return points;
  const cutoff = new Date(endDate.getTime());
  cutoff.setUTCMonth(cutoff.getUTCMonth() - Math.max(1, Number(months) || DASHBOARD_INPUT_DEFAULTS.lookbackMonths));
  const filtered = points.filter((point) => {
    const pointDate = parseDateString(point.date);
    return pointDate && pointDate >= cutoff;
  });
  return filtered.length >= 2 ? filtered : points.slice(-Math.min(points.length, 2));
}

function rebalanceBucket(dateText, frequency) {
  const parts = String(dateText || '').split('-').map((part) => Number(part));
  if (parts.length < 3 || parts.some((part) => !Number.isFinite(part))) return String(dateText || '');
  const [year, month, day] = parts;
  if (frequency === 'QE') return `${year}-Q${Math.floor((month - 1) / 3) + 1}`;
  if (frequency === 'W') return `${year}-${String(month).padStart(2, '0')}-W${Math.ceil(day / 7)}`;
  return `${year}-${String(month).padStart(2, '0')}`;
}

function isScenarioRebalance(points, index, frequency) {
  if (index <= 0 || index >= points.length) return false;
  return rebalanceBucket(points[index].date, frequency) !== rebalanceBucket(points[index - 1].date, frequency);
}

function allocationConcentration(allocation) {
  const weights = (allocation?.weighted || []).map((row) => Number(row.display_weight) || 0).filter((value) => value > 0);
  if (!weights.length) return 0;
  return weights.reduce((sum, value) => sum + value * value, 0);
}

function adjustedScenarioPointsFromRaw(rawPoints, params, allocation) {
  if (rawPoints.length < 2) return rawPoints;
  const hasAllocation = Array.isArray(allocation?.weighted) && allocation.weighted.length > 0;
  const invested = hasAllocation ? Math.max(0, Math.min(1, Number(allocation?.investedTotal) || 0)) : 1;
  const topN = Math.max(1, Number(params.topN) || DASHBOARD_INPUT_DEFAULTS.topN);
  const concentration = hasAllocation ? allocationConcentration(allocation) : 1 / topN;
  const equalConcentration = 1 / topN;
  const concentrationTilt = Math.max(-0.5, Math.min(2.5, concentration / Math.max(equalConcentration, 1e-6) - 1));
  const exposureMultiplier = Math.max(0.05, Math.min(1.45, invested * (1 + 0.10 * concentrationTilt)));
  const turnoverProxy = Math.max(0, Math.min(2, 0.35 + 0.20 * Math.max(0, concentrationTilt)));
  const adjusted = [{ ...rawPoints[0], equity: 1, drawdown: 0 }];
  let equity = 1;
  let peak = 1;
  for (let index = 1; index < rawPoints.length; index += 1) {
    const previous = Number(rawPoints[index - 1].equity);
    const current = Number(rawPoints[index].equity);
    let dailyReturn = previous > 0 && Number.isFinite(previous) && Number.isFinite(current)
      ? current / previous - 1
      : 0;
    dailyReturn *= exposureMultiplier;
    if (isScenarioRebalance(rawPoints, index, params.rebalanceFrequency)) {
      dailyReturn -= turnoverProxy * params.totalCostRate;
    }
    equity *= Math.max(0.0001, 1 + dailyReturn);
    peak = Math.max(peak, equity);
    adjusted.push({
      date: rawPoints[index].date,
      equity,
      drawdown: peak > 0 ? equity / peak - 1 : 0,
      scenario_exposure: exposureMultiplier,
      scenario_turnover_proxy: turnoverProxy,
    });
  }
  return adjusted;
}

function scenarioAdjustedSeriesPoints(series, date, params, allocation) {
  const rawPoints = lookbackFilteredPoints(seriesPointsThroughDate(series, date, 2000), params.lookbackMonths);
  return adjustedScenarioPointsFromRaw(rawPoints, params, allocation);
}

function tradingDaysForWindow(run, windowKey) {
  const period = (run.periods || []).find((item) => item.key === windowKey);
  const days = Number(period?.trading_days);
  if (Number.isFinite(days) && days > 0) return Math.round(days);
  const fallback = { '1W': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252 };
  return fallback[windowKey] || Math.max(21, Math.round((Number(inputScenarioParameters().lookbackMonths) || 12) * 21));
}

function scenarioLookbackTradingDays(params) {
  const months = Number(params?.lookbackMonths);
  if (!Number.isFinite(months) || months <= 0) return null;
  return Math.max(1, Math.round(months * 21));
}

function scenarioWindowTradingDays(run, windowKey, params) {
  const windowDays = tradingDaysForWindow(run, windowKey);
  const lookbackDays = scenarioLookbackTradingDays(params);
  return lookbackDays ? Math.max(1, Math.min(windowDays, lookbackDays)) : windowDays;
}

function scenarioAdjustedWindowPoints(run, factor, date, windowKey, params, allocation) {
  const series = factorBacktestSeries(run, factor);
  const rawPoints = lookbackFilteredPoints(seriesPointsThroughDate(series, date, 2000), params.lookbackMonths);
  if (rawPoints.length < 2) return [];
  const tradingDays = scenarioWindowTradingDays(run, windowKey, params);
  const windowPoints = rawPoints.slice(-Math.min(rawPoints.length, tradingDays + 1));
  return adjustedScenarioPointsFromRaw(windowPoints, params, allocation);
}

function cumulativeReturnFromPoints(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const first = Number(points[0].equity);
  const last = Number(points.at(-1).equity);
  if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
  return last / first - 1;
}

function rawPeriodRows(run, date, windowKey) {
  const matrix = periodMatrixEntry(run, date, windowKey);
  if (matrix && Array.isArray(matrix.factors)) {
    return matrix.factors.map((name, index) => ({
      factor: name,
      raw_rank: index + 1,
      rank: index + 1,
      period_return: optionalNumber(matrix.returns?.[index]),
      raw_period_return: optionalNumber(matrix.returns?.[index]),
      window_label: matrix.window_label || windowKey,
      factor_count: matrix.factor_count || matrix.factors.length,
    }));
  }
  return (run.factor_period_rankings || [])
    .filter((row) => row.date === date && row.window === windowKey)
    .map((row, index) => ({
      factor: row.factor,
      raw_rank: row.rank || index + 1,
      rank: row.rank || index + 1,
      period_return: optionalNumber(row.period_return),
      raw_period_return: optionalNumber(row.period_return),
      window_label: row.window_label || windowKey,
      factor_count: row.factor_count || null,
    }));
}

function scenarioFactorStats(run, date, windowKey, factor, params = inputScenarioParameters()) {
  const rawStats = periodFactorStats(run, date, windowKey, factor) || { factor, rank: null, period_return: null };
  const allocation = scenarioAllocationForFactor(run, date, windowKey, factor, params.topN, params.maxWeight).allocation;
  const points = scenarioAdjustedWindowPoints(run, factor, date, windowKey, params, allocation);
  const scenarioReturn = cumulativeReturnFromPoints(points);
  return {
    ...rawStats,
    factor,
    raw_period_return: rawStats?.period_return ?? null,
    period_return: scenarioReturn ?? rawStats?.period_return ?? null,
    scenario_adjusted: scenarioReturn !== null,
    scenario_points: points,
    scenario_allocation: allocation,
    scenario_inputs: params,
  };
}

function scenarioPeriodRows(run, date, windowKey, params = inputScenarioParameters()) {
  const rows = rawPeriodRows(run, date, windowKey);
  const enhanced = rows.map((row) => {
    const scenario = scenarioFactorStats(run, date, windowKey, row.factor, params);
    return {
      ...row,
      raw_period_return: row.raw_period_return ?? row.period_return,
      period_return: scenario.period_return,
      scenario_adjusted: scenario.scenario_adjusted,
      scenario_points: scenario.scenario_points,
      scenario_allocation: scenario.scenario_allocation,
    };
  });
  return enhanced
    .sort((a, b) => {
      const ar = Number(a.period_return);
      const br = Number(b.period_return);
      if (Number.isFinite(ar) && Number.isFinite(br) && ar !== br) return br - ar;
      if (Number.isFinite(br) !== Number.isFinite(ar)) return Number.isFinite(br) ? 1 : -1;
      return Number(a.raw_rank || 9999) - Number(b.raw_rank || 9999);
    })
    .map((row, index) => ({
      ...row,
      rank: index + 1,
      factor_count: row.factor_count || enhanced.length,
    }));
}

function scenarioBestStats(run, date, windowKey, params = inputScenarioParameters()) {
  return scenarioPeriodRows(run, date, windowKey, params)[0] || periodBestStats(run, date, windowKey);
}

function renderBacktestChart() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const benchmark = benchmarkBacktestSeries(run);
  const params = inputScenarioParameters();
  const best = scenarioBestStats(run, date, windowKey, params);
  const selectedAllocation = scenarioAllocationForFactor(run, date, windowKey, factor, params.topN, params.maxWeight).allocation;
  const selectedSeries = normalizedLine(scenarioAdjustedSeriesPoints(factorBacktestSeries(run, factor), date, params, selectedAllocation));
  const bestAllocation = best?.factor
    ? scenarioAllocationForFactor(run, date, windowKey, best.factor, params.topN, params.maxWeight).allocation
    : null;
  const bestMetricSeries = best?.factor
    ? normalizedLine(scenarioAdjustedSeriesPoints(factorBacktestSeries(run, best.factor), date, params, bestAllocation))
    : [];
  const bestSeries = best?.factor && best.factor !== factor ? bestMetricSeries : [];
  const benchmarkSeries = normalizedLine(lookbackFilteredPoints(seriesPointsThroughDate(benchmark, date, 2000), params.lookbackMonths));
  const benchmarkLabel = benchmark?.label_ko || benchmark?.symbol || run.summary?.chart_benchmark || '나스닥 벤치마크';
  const target = document.querySelector('#backtest-chart');
  target.replaceChildren();
  setText(
    '#backtest-chart-meta',
    `${date || '-'} 기준 · 브라우저 프록시/민감도 뷰 · 최근 ${params.lookbackMonths}개월 · 선택 ${factor || '-'}${best?.factor ? ` · 기간 최고 ${best.factor}` : ''}${benchmarkSeries.length ? ` · 벤치마크 ${benchmarkLabel}` : ''} · ${rebalanceFrequencyLabel(params.rebalanceFrequency)} · 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps · 최대 ${formatPercent(params.maxWeight)} · 저장된 팩터 곡선을 현재 비중 집중도와 비용 가정으로 조정`
  );
  if (!selectedSeries.length) {
    appendEmpty('#backtest-chart', '선택 팩터의 최근 백테스트 추이 데이터가 없습니다. 기간 최고 팩터 데이터를 대신 표시하지 않습니다.');
    renderPerformanceMetricsTable([]);
    return;
  }
  const allPoints = [...selectedSeries, ...bestSeries, ...benchmarkSeries];
  const allValues = allPoints.map((point) => point.normalized).filter((value) => Number.isFinite(value));
  const returnValues = allValues.map((value) => value - 1);
  const tickReturns = niceReturnTicks(Math.min(...returnValues, 0), Math.max(...returnValues, 0));
  const minValue = Math.min(...tickReturns) + 1;
  const maxValue = Math.max(...tickReturns) + 1;
  const allDates = [...new Set(allPoints.map((point) => point.date).filter(Boolean))].sort();
  const dateToIndex = new Map(allDates.map((pointDate, index) => [pointDate, index]));
  const width = 760;
  const height = 260;
  const plot = { left: 68, right: 18, top: 18, bottom: 50 };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '선택 팩터, 기간 최고 팩터, 나스닥 벤치마크의 최근 백테스트 누적 성과 비교');
  const yFor = (value) => height - plot.bottom - ((value - minValue) / Math.max(0.000001, maxValue - minValue)) * plotHeight;
  const xFor = (point) => {
    const index = dateToIndex.get(point.date) ?? 0;
    return plot.left + (allDates.length <= 1 ? 0 : index / (allDates.length - 1) * plotWidth);
  };
  tickReturns.forEach((tickReturn) => {
    const y = yFor(tickReturn + 1);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', String(plot.left));
    line.setAttribute('x2', String(width - plot.right));
    line.setAttribute('y1', String(y));
    line.setAttribute('y2', String(y));
    line.setAttribute('class', 'line-grid');
    svg.appendChild(line);
    appendSvgText(svg, formatPercentTick(tickReturn), plot.left - 9, y + 4, 'axis-label', 'end');
  });
  const yAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  yAxis.setAttribute('x1', String(plot.left));
  yAxis.setAttribute('x2', String(plot.left));
  yAxis.setAttribute('y1', String(plot.top));
  yAxis.setAttribute('y2', String(height - plot.bottom));
  yAxis.setAttribute('class', 'axis-line');
  svg.appendChild(yAxis);
  const xAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  xAxis.setAttribute('x1', String(plot.left));
  xAxis.setAttribute('x2', String(width - plot.right));
  xAxis.setAttribute('y1', String(height - plot.bottom));
  xAxis.setAttribute('y2', String(height - plot.bottom));
  xAxis.setAttribute('class', 'axis-line');
  svg.appendChild(xAxis);
  dateTickMarks(allDates).forEach((tickMark) => {
    const { index } = tickMark;
    const x = plot.left + (allDates.length <= 1 ? 0 : index / (allDates.length - 1) * plotWidth);
    const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    tick.setAttribute('x1', String(x));
    tick.setAttribute('x2', String(x));
    tick.setAttribute('y1', String(height - plot.bottom));
    tick.setAttribute('y2', String(height - plot.bottom + 5));
    tick.setAttribute('class', 'axis-line');
    svg.appendChild(tick);
    appendSvgText(svg, tickMark.label, x, height - plot.bottom + 19, 'axis-label');
  });
  appendSvgText(svg, 'X축: 날짜', plot.left + plotWidth / 2, height - 5, 'axis-title');
  const yTitle = appendSvgText(svg, 'Y축: 누적 성과', 13, plot.top + plotHeight / 2, 'axis-title');
  yTitle.setAttribute('transform', `rotate(-90 13 ${plot.top + plotHeight / 2})`);
  const toPolyline = (points) => points.map((point) => {
    const x = xFor(point);
    const y = yFor(point.normalized);
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
  appendLine(benchmarkSeries, 'benchmark');
  target.appendChild(svg);

  const legend = document.createElement('div');
  legend.className = 'line-legend';
  const selectedReturn = selectedSeries.at(-1)?.normalized - 1;
  const bestReturn = bestSeries.length ? bestSeries.at(-1)?.normalized - 1 : null;
  const benchmarkReturn = benchmarkSeries.length ? benchmarkSeries.at(-1)?.normalized - 1 : null;
  const selectedDrawdown = selectedSeries.at(-1)?.drawdown;
  const bestDrawdown = bestSeries.length ? bestSeries.at(-1)?.drawdown : null;
  const benchmarkDrawdown = benchmarkSeries.length ? benchmarkSeries.at(-1)?.drawdown : null;
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
  if (benchmarkSeries.length) {
    const benchmarkLegend = document.createElement('span');
    const benchmarkDot = document.createElement('span');
    benchmarkDot.className = 'legend-dot benchmark';
    benchmarkLegend.appendChild(benchmarkDot);
    benchmarkLegend.append(`${benchmarkLabel}: 구간 ${formatPercent(benchmarkReturn)} · 낙폭 ${formatPercent(benchmarkDrawdown)}`);
    legend.appendChild(benchmarkLegend);
  }
  target.appendChild(legend);
  renderPerformanceMetricsTable([
    { key: 'selected', label: `선택 팩터 ${factor || '-'}`, points: selectedSeries },
    {
      key: 'best',
      label: `기간 최고 팩터 ${best?.factor || '-'}`,
      points: bestMetricSeries.length ? bestMetricSeries : selectedSeries,
    },
    { key: 'benchmark', label: benchmarkLabel, points: benchmarkSeries },
  ]);
}

function renderPerformanceMetricsTable(seriesList) {
  const target = document.querySelector('#performance-metrics-table');
  if (!target) return;
  target.replaceChildren();
  const availableSeries = (seriesList || []).filter((series) => Array.isArray(series.points) && series.points.length >= 2);
  if (!availableSeries.length) {
    appendEmpty('#performance-metrics-table', '성과 지표를 계산할 수 있는 누적 성과 데이터가 없습니다.');
    return;
  }

  const heading = document.createElement('div');
  heading.className = 'performance-metrics-heading';
  const headingText = document.createElement('div');
  const title = document.createElement('h4');
  title.textContent = '기간별 프록시 성과 지표 비교';
  const note = document.createElement('p');
  note.textContent = '각 기간 카드에서 같은 지표의 선택 팩터·기간 최고 팩터·나스닥 값을 한 줄로 비교합니다. 선택/기간 최고 팩터 값은 새 백엔드 재백테스트가 아니라 저장된 팩터 누적 성과를 현재 입력값의 비중 집중도·리밸런싱·비용 가정으로 조정한 브라우저 프록시입니다. 샤프·변동성·소르티노·칼마·CVaR 산식은 같은 방식으로 적용하고, CVaR은 최악 5% 일간 손실 평균입니다. 실제 일별 구성종목 재매매 결과로 해석하지 마세요.';
  headingText.append(title, note);
  heading.appendChild(headingText);
  target.appendChild(heading);

  const metricCache = new Map(availableSeries.map((series) => [
    series.key,
    new Map(PERFORMANCE_PERIODS.map((period) => [period.key, performanceMetrics(series.points, period)])),
  ]));
  const shortSeriesLabel = (series) => ({
    selected: '선택 팩터',
    best: '기간 최고',
    benchmark: '나스닥',
  })[series.key] || series.label;

  const grid = document.createElement('div');
  grid.className = 'performance-period-grid';
  PERFORMANCE_PERIODS.forEach((period) => {
    const card = document.createElement('section');
    card.className = 'performance-period-card';
    const periodTitle = document.createElement('h5');
    periodTitle.textContent = period.label;
    card.appendChild(periodTitle);

    const wrap = document.createElement('div');
    wrap.className = 'performance-table-wrap';
    const table = document.createElement('table');
    table.className = 'performance-table';
    table.setAttribute('aria-label', `${period.label} 선택 팩터, 기간 최고 팩터, 나스닥 벤치마크 성과 지표 비교`);
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    appendHeader(header, '지표');
    availableSeries.forEach((series) => {
      const th = document.createElement('th');
      const label = document.createElement('span');
      label.className = `series-name ${series.key}`;
      label.textContent = shortSeriesLabel(series);
      th.appendChild(label);
      header.appendChild(th);
    });
    thead.appendChild(header);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    PERFORMANCE_METRICS.forEach((metric) => {
      const tr = document.createElement('tr');
      appendCell(tr, metric.label, { strong: true });
      availableSeries.forEach((series) => {
        const metrics = metricCache.get(series.key)?.get(period.key);
        const value = metrics?.[metric.key];
        const signedMetric = ['cumulativeReturn', 'maxDrawdown', 'cvar'].includes(metric.key);
        const className = signedMetric && Number.isFinite(Number(value)) ? classForNumber(value) : '';
        appendCell(tr, metric.formatter(value), { className });
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    card.appendChild(wrap);
    grid.appendChild(card);
  });
  target.appendChild(grid);
}

function normalizeDailyActualRows(sourceRows, sourceMeta = {}) {
  return (sourceRows || [])
    .map((row, index) => {
      if (Array.isArray(row)) {
        return {
          date: sourceMeta.date || '-',
          window: sourceMeta.window || '-',
          windowLabel: sourceMeta.window_label || sourceMeta.window || '-',
          factor: sourceMeta.factor || '-',
          rank: index + 1,
          symbol: row[0],
          actualWeight: Number(row[1]),
          score: Number(row[2]),
          weightDate: sourceMeta.weight_date || sourceMeta.date || '-',
          scoreDate: sourceMeta.score_date || sourceMeta.date || '-',
          source: sourceMeta.weight_source || '백테스트 일별 보유 비중',
        };
      }
      return {
        date: row.date || sourceMeta.date || '-',
        window: row.window || sourceMeta.window || '-',
        windowLabel: row.window_label || sourceMeta.window_label || row.window || '-',
        factor: row.factor || sourceMeta.factor || '-',
        rank: row.rank || index + 1,
        symbol: row.symbol,
        actualWeight: Number(row.default_weight ?? row.weight),
        score: Number(row.score),
        weightDate: row.weight_date || sourceMeta.weight_date || row.date || sourceMeta.date || '-',
        scoreDate: row.score_date || sourceMeta.score_date || row.date || sourceMeta.date || '-',
        source: row.weight_source || sourceMeta.weight_source || '백테스트 일별 보유 비중',
      };
    })
    .filter((row) => row.symbol && Number.isFinite(row.actualWeight) && row.actualWeight > 0)
    .sort((a, b) => (
      String(b.date).localeCompare(String(a.date))
      || Number(a.rank || 9999) - Number(b.rank || 9999)
      || Number(b.actualWeight) - Number(a.actualWeight)
    ));
}

function scenarioAllocationFromDailyRows(rows, topN, maxWeight) {
  const scoreRows = rows.map((row) => ({
    symbol: row.symbol,
    score: Number.isFinite(Number(row.score)) ? Number(row.score) : Number(row.actualWeight) || 0,
  }));
  return computeScenarioAllocation(scoreRows, topN, maxWeight);
}

function selectedDailyWeightRows(run, date, windowKey, factor, topN, maxWeight) {
  const exactSnapshot = factorWeightSnapshot(run, date, windowKey, factor);
  const snapshotCandidates = (run.factor_weight_snapshots || [])
    .filter((snapshot) => snapshot.factor === factor && snapshot.window === windowKey && String(snapshot.date || '') <= String(date || '9999-99-99'))
    .sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  const snapshot = exactSnapshot || snapshotCandidates[0] || null;
  const historyRows = (run.holdings || [])
    .filter((row) => row.factor === factor && row.window === windowKey && String(row.date || '') <= String(date || '9999-99-99'));
  const historyDates = [...new Set(historyRows.map((row) => row.date).filter(Boolean))]
    .sort((a, b) => String(b).localeCompare(String(a)))
    .slice(0, 5);
  const groupedRows = [];
  historyDates.forEach((day) => {
    const rowsForDay = normalizeDailyActualRows(historyRows.filter((row) => row.date === day))
      .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
      .slice(0, topN);
    const allocation = scenarioAllocationFromDailyRows(rowsForDay, topN, maxWeight);
    const scenarioBySymbol = new Map((allocation.weighted || []).map((row) => [String(row.symbol), row]));
    rowsForDay.forEach((row) => {
      const scenarioWeight = Number(scenarioBySymbol.get(String(row.symbol))?.display_weight) || 0;
      groupedRows.push({
        ...row,
        scenarioWeight,
        deltaWeight: scenarioWeight - row.actualWeight,
        scenarioSource: 'daily_holding_score_reweight',
      });
    });
  });

  if (groupedRows.length) {
    return {
      rows: groupedRows,
      sourceKind: 'historical_holdings',
      snapshot,
      dateCount: historyDates.length,
      exactDate: historyDates.includes(date),
    };
  }

  if (snapshot) {
    const rowsForSnapshot = normalizeDailyActualRows(snapshot.rows || [], snapshot)
      .sort((a, b) => Number(a.rank || 9999) - Number(b.rank || 9999))
      .slice(0, topN);
    const allocation = scenarioAllocationFromDailyRows(rowsForSnapshot, topN, maxWeight);
    const scenarioBySymbol = new Map((allocation.weighted || []).map((row) => [String(row.symbol), row]));
    return {
      rows: rowsForSnapshot.map((row) => {
        const scenarioWeight = Number(scenarioBySymbol.get(String(row.symbol))?.display_weight) || 0;
        return {
          ...row,
          scenarioWeight,
          deltaWeight: scenarioWeight - row.actualWeight,
          scenarioSource: 'factor_weight_snapshot_reweight',
        };
      }),
      sourceKind: exactSnapshot ? 'exact_weight_snapshot' : 'nearest_weight_snapshot',
      snapshot,
      dateCount: 1,
      exactDate: Boolean(exactSnapshot),
    };
  }

  const scenario = currentWeightedHoldings();
  return {
    rows: (scenario.weighted || []).slice(0, topN).map((row, index) => ({
      date,
      window: windowKey,
      windowLabel: scenario.windowLabel,
      factor,
      rank: row.display_rank || index + 1,
      symbol: row.symbol,
      actualWeight: null,
      scenarioWeight: Number(row.display_weight) || 0,
      deltaWeight: null,
      score: row.score,
      weightDate: date,
      scoreDate: scenario.scoreDate || date,
      source: scenario.scoreScope || '점수 스냅샷 기반 시나리오',
      scenarioSource: 'score_snapshot_only',
    })),
    sourceKind: 'score_snapshot_only',
    snapshot: null,
    dateCount: 1,
    exactDate: false,
  };
}

function renderDailyWeightsAnalysis() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  const topN = params.topN;
  const maxWeight = params.maxWeight;
  const { rows, sourceKind, snapshot, dateCount, exactDate } = selectedDailyWeightRows(run, date, windowKey, factor, topN, maxWeight);

  setText(
    '#daily-weight-analysis-note',
    sourceKind === 'historical_holdings'
      ? `${date || '-'} 이하 최근 ${dateCount}개 보유일의 선택 팩터 ${factor || '-'} 비중입니다. 리밸런싱 빈도와 비용 입력은 저장 보유 비중 자체가 아니라 현재 입력 시나리오/성과 프록시 비교에만 반영됩니다. 종목을 열로 배치해 날짜별 저장 비중과 현재 입력 시나리오 비중을 바로 비교합니다.`
      : snapshot
      ? `${snapshot.date || date || '-'} 기준 선택 팩터 ${factor || '-'}의 ${exactDate ? '정확한' : '가장 가까운'} 보유 비중 스냅샷입니다. 종목 열마다 저장/현재 입력 비중을 함께 표시합니다.`
      : `${date || '-'} 기준 선택 팩터 ${factor || '-'}의 저장 보유 비중이 없어 점수 스냅샷 기반 시나리오 비중만 종목별로 표시합니다.`,
  );

  const table = document.querySelector('#daily-weights-table');
  const thead = document.querySelector('#daily-weights-table thead');
  const tbody = document.querySelector('#daily-weights-table tbody');
  if (!table || !thead || !tbody) return;

  tbody.replaceChildren();
  const scenario = currentWeightedHoldings();
  const scenarioRows = Array.isArray(scenario.weighted) ? scenario.weighted : [];
  const scenarioBySymbol = new Map(scenarioRows.map((row) => [String(row.symbol), row]));
  const symbols = [
    ...new Set([
      ...rows.map((row) => row.symbol).filter(Boolean),
      ...scenarioRows.map((row) => row.symbol).filter(Boolean),
    ]),
  ].slice(0, Math.max(1, Math.min(topN, 24)));
  const headerRow = document.createElement('tr');
  appendHeaderCell(headerRow, '비중일');
  appendHeaderCell(headerRow, '기간');
  symbols.forEach((symbol) => {
    appendHeaderCell(headerRow, `${symbol} 저장`);
    appendHeaderCell(headerRow, `${symbol} 현재`);
  });
  thead.replaceChildren(headerRow);

  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = Math.max(symbols.length * 2 + 2, 3);
    td.textContent = '선택한 기준일과 팩터에 표시할 일별 투자 비중 데이터가 없습니다.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const groups = new Map();
  rows.forEach((row) => {
    const key = `${row.weightDate || row.date || '-'}|${row.windowLabel || row.window || '-'}`;
    if (!groups.has(key)) {
      groups.set(key, {
        date: row.weightDate || row.date || '-',
        windowLabel: row.windowLabel || row.window || '-',
        bySymbol: new Map(),
      });
    }
    if (row.symbol) groups.get(key).bySymbol.set(row.symbol, row);
  });

  [...groups.values()]
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .forEach((group) => {
      const tr = document.createElement('tr');
      appendCell(tr, group.date);
      appendCell(tr, group.windowLabel);
      symbols.forEach((symbol) => appendWeightMatrixCells(tr, group.bySymbol.get(symbol), scenarioBySymbol.get(String(symbol))));
      tbody.appendChild(tr);
    });
}

function appendHeaderCell(tr, text) {
  const th = document.createElement('th');
  th.scope = 'col';
  th.textContent = text;
  tr.appendChild(th);
}

function appendWeightMatrixCells(tr, row, scenarioRow = null) {
  const actual = document.createElement('td');
  actual.className = 'weight-matrix-cell';
  if (row && row.actualWeight !== null) {
    const primary = document.createElement('strong');
    primary.textContent = formatPercent(row.actualWeight);
    const secondary = document.createElement('small');
    secondary.textContent = row.source || (row.scoreDate ? `신호일 ${row.scoreDate}` : '저장 비중');
    actual.title = `${row.symbol || ''} ${row.scoreDate ? `신호일 ${row.scoreDate}` : ''}`.trim();
    actual.append(primary, secondary);
  } else {
    actual.textContent = '-';
  }
  tr.appendChild(actual);

  const scenario = document.createElement('td');
  scenario.className = 'weight-matrix-cell';
  const scenarioWeight = row ? Number(row.scenarioWeight) : Number(scenarioRow?.display_weight);
  if (Number.isFinite(scenarioWeight) && scenarioWeight > 0) {
    const primary = document.createElement('strong');
    primary.textContent = formatPercent(scenarioWeight);
    const secondary = document.createElement('small');
    const parts = [];
    if (row && row.deltaWeight !== null) parts.push(`차이 ${formatPercent(row.deltaWeight)}`);
    const score = row?.score ?? scenarioRow?.score;
    if (Number.isFinite(Number(score))) parts.push(`신호 ${formatNumber(score)}`);
    if (!row && scenarioRow) parts.push('현재 입력 시나리오');
    secondary.textContent = parts.join(' · ') || '시나리오 비중';
    scenario.append(primary, secondary);
  } else {
    scenario.textContent = '-';
  }
  tr.appendChild(scenario);
}

function parseSelectedFactorMethod(factor, option = {}) {
  const text = String(factor || '');
  const override = FACTOR_METHOD_OVERRIDES[text] || null;
  const category = humanFactorCategory(override?.category || option.category || 'unknown');
  const base = {
    category,
    formulaLabel: override?.formula || '팩터별 가격/거래량·재무 신호 산식',
    lookback: '팩터명 또는 카탈로그 정의 구간',
    skip: '팩터별 정의에 따름',
    score: override
      ? `${text} 원자료 산식은 ${override.formula}입니다. 각 종목에 같은 산식을 적용한 뒤 점수가 높은 순서로 후보를 정렬합니다.`
      : '종목별 가격 기반 신호를 계산한 뒤 값이 큰 순서로 순위를 매깁니다.',
    caveat: override
      ? `${override.description} 검증 메모: ${override.validation}`
      : option.description_ko || option.description || '세부 설명 정보가 제한적이므로 팩터명과 카테고리 기반으로 해석합니다.',
  };
  let match = text.match(/^mom_(\d+)_(\d+)$/);
  if (match) {
    const lookback = Number(match[1]);
    const skip = Number(match[2]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t-${skip}m) / P_i(t-${lookback + skip}m) - 1`,
      lookback: `최근 ${skip}개월을 제외한 직전 ${lookback}개월 가격 변화`,
      skip: `${skip}개월 스킵/제외`,
      score: `각 종목 i에 대해 최근 ${skip}개월을 제외한 직전 ${lookback}개월 누적수익률을 계산합니다. 즉 대략 P_i(t-${skip}m) / P_i(t-${lookback + skip}m) - 1이며, 값이 큰 종목이 상위 모멘텀 후보입니다.`,
      caveat: `${base.caveat} 최근 과열/단기 반전 오염을 줄이기 위해 가장 최근 ${skip}개월은 점수 계산 구간에서 제외합니다.`,
    };
  }
  match = text.match(/^mom_(\d+)m$/);
  if (match) {
    const lookback = Number(match[1]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / P_i(t-${lookback}m) - 1`,
      lookback: `${lookback}개월 가격 변화`,
      skip: '명시적 스킵 없음',
      score: `각 종목의 최근 ${lookback}개월 누적수익률을 계산하고 높은 순서로 정렬합니다. 원자료 산식은 조정종가 기준 가격 변화율입니다.`,
      caveat: `${base.caveat} 단순 기간 모멘텀은 빠른 추세를 직접 보지만 단기 과열과 회전율에 더 민감할 수 있습니다.`,
    };
  }
  match = text.match(/^mom_(\d+)d$/);
  if (match) {
    const days = Number(match[1]);
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / P_i(t-${days}d) - 1`,
      lookback: `${days}거래일`,
      skip: '명시적 스킵 없음',
      score: `최근 ${days}거래일 내외의 단기 가격 변화를 비교해 단기 모멘텀이 강한 종목을 위로 정렬합니다.`,
      caveat: `${base.caveat} 단기 모멘텀 팩터는 회전율과 반전 위험이 커서 비용/슬리피지 민감도를 함께 봐야 합니다.`,
    };
  }
  match = text.match(/^accel_(\d+)m_vs_(\d+)m$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `${match[1]}개월 모멘텀 - ${match[2]}개월 모멘텀`,
      lookback: `${match[1]}개월과 ${match[2]}개월 수익률 비교`,
      skip: '팩터 정의의 skip 값 적용',
      score: `짧은 기간 모멘텀이 긴 기간 모멘텀보다 얼마나 개선됐는지 계산합니다. 값이 클수록 최근 리더십이 가속된 종목입니다.`,
      caveat: `${base.caveat} 가속도 계열은 추세 변화 속도를 보므로 단순 장기 모멘텀보다 노이즈에 민감할 수 있습니다.`,
    };
  }
  match = text.match(/^high_(\d+)w$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / rolling_high_${match[1]}w - 1`,
      lookback: `${match[1]}주 고점/현재가 비교`,
      skip: '명시적 스킵 없음',
      score: `현재 가격이 ${match[1]}주 고점에 얼마나 가까운지로 추세 지속성을 평가합니다. 0에 가까울수록 고점 근접도가 높습니다.`,
      caveat: `${base.caveat} 고점 근접 팩터는 강한 추세를 빠르게 포착하지만 추세 말기 변동성에 유의해야 합니다.`,
    };
  }
  match = text.match(/^breakout_(\d+)d$/);
  if (match) {
    return {
      ...base,
      formulaLabel: override?.formula || `score_i = P_i(t) / prior_high_${match[1]}d - 1 + 확인 모멘텀`,
      lookback: `${match[1]}거래일 가격 범위`,
      skip: '명시적 스킵 없음',
      score: `최근 ${match[1]}거래일 가격 범위에서 상단 돌파/근접 정도와 확인 모멘텀을 함께 평가합니다.`,
      caveat: `${base.caveat} 돌파 팩터는 추세 시작을 포착하려 하지만 false breakout과 비용 민감도가 있습니다.`,
    };
  }
  if (text.includes('winsorized') || text.includes('gap_resistant') || text.includes('jump_excluded') || text.includes('median_return')) {
    return {
      ...base,
      lookback: '주로 63~252거래일 견고화 구간',
      score: `${base.score} 급등락·단일 점프·극단 일수익률 영향을 줄이는 견고화 처리를 포함합니다.`,
      caveat: `${base.caveat} 견고화 계열은 한두 번의 급등락에 덜 끌려가지만, 실제 급격한 추세 전환을 일부 늦게 반영할 수 있습니다.`,
    };
  }
  if (text.includes('risk') || text.includes('vol') || text.includes('ulcer') || text.includes('drawdown') || text.includes('tail')) {
    return {
      ...base,
      lookback: '모멘텀 구간과 63~252거래일 위험 구간',
      score: `${base.score} 상승률을 변동성, 낙폭, 하방위험, 좌측 꼬리위험 같은 위험 지표로 보정합니다.`,
      caveat: `${base.caveat} 위험조정 계열은 단순 수익률보다 안정성을 선호하지만 강한 고변동 추세를 낮게 볼 수 있습니다.`,
    };
  }
  if (text.includes('ma_') || text.includes('trend') || text.includes('range_position') || text.includes('price_vs_ma')) {
    return {
      ...base,
      lookback: '20~252거래일 추세·이동평균·가격 범위 구간',
      score: `${base.score} 이동평균 기울기, 추세 정렬, 가격 범위 내 위치 등을 이용해 추세 품질을 평가합니다.`,
      caveat: `${base.caveat} 추세 품질 계열은 방향성과 지속성을 함께 보지만 횡보장에서는 신호가 둔화될 수 있습니다.`,
    };
  }
  if (text.includes('relative_strength') || text.includes('residual') || text.includes('excess_ir') || text.includes('up_down_capture')) {
    return {
      ...base,
      lookback: '주로 126~252거래일 횡단면/시장상대 구간',
      score: `${base.score} 동일 후보군 또는 시장 프록시 대비 초과 성과·상대 순위·상승/하락 참여도를 비교합니다.`,
      caveat: `${base.caveat} 상대강도 계열은 후보군 구성과 시장 프록시 변화에 민감하므로 단독 투자 결론보다 비교 진단으로 보세요.`,
    };
  }
  return base;
}

function appendMethodItem(target, label, value) {
  const item = document.createElement('div');
  item.className = 'method-item';
  const strong = document.createElement('strong');
  strong.textContent = label;
  const small = document.createElement('small');
  small.textContent = textValue(value);
  item.append(strong, small);
  target.appendChild(item);
}

function renderSelectedFactorMethod() {
  const run = currentRun();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  const option = factorOptions(run).find((item) => item.factor === factor) || {};
  const method = parseSelectedFactorMethod(factor, option);
  setText('#selected-factor-method-title', factor || '-');
  setText('#selected-factor-method-badge', `${method.category} · 브라우저 시나리오 설명`);
  setText(
    '#selected-factor-method-summary',
    `${factor || '-'} 계산법: ${method.score} 현재 화면의 비중/성과 비교는 이 점수 순위를 기반으로 최근 ${params.lookbackMonths}개월, 상위 ${params.topN}개, 종목당 최대 ${formatPercent(params.maxWeight)}, ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 리밸런싱, 비용 ${(params.transactionCostBps + params.slippageBps).toFixed(0)}bps 가정을 적용한 브라우저 시나리오/민감도 프록시입니다.`,
  );
  const steps = document.querySelector('#selected-factor-method-steps');
  if (steps) {
    steps.replaceChildren();
    appendMethodItem(steps, '팩터 분류', method.category);
    appendMethodItem(steps, '핵심 산식', method.formulaLabel);
    appendMethodItem(steps, '관찰 구간', method.lookback);
    appendMethodItem(steps, '최근 구간 제외', method.skip);
    appendMethodItem(steps, '비중 적용', `점수 상위 ${params.topN}개를 점수 비례로 배분하고 종목당 ${formatPercent(params.maxWeight)} 상한을 적용합니다.`);
    appendMethodItem(steps, '성과 적용', `저장된 팩터 누적성과를 비중 집중도와 ${rebalanceFrequencyLabel(params.rebalanceFrequency)} 비용 프록시로 조정합니다.`);
  }
  setText(
    '#selected-factor-method-note',
    `${method.caveat} 이 페이지는 서버에서 전체 일별 구성종목을 재백테스트한 결과가 아니라, 저장된 점수/비중 스냅샷과 팩터 누적성과를 현재 입력값으로 다시 해석한 브라우저 시나리오/프록시입니다.`,
  );
}

function renderPeriodRankingTable() {
  const run = currentRun();
  const date = selectedDate();
  const windowKey = selectedWindow();
  const factor = selectedFactor();
  const params = inputScenarioParameters();
  let rows = scenarioPeriodRows(run, date, windowKey, params);
  const selectedRow = rows.find((row) => row.factor === factor);
  rows = rows.slice(0, 40);
  if (selectedRow && !rows.some((row) => row.factor === selectedRow.factor)) rows.push(selectedRow);
  const tbody = document.querySelector('#period-ranking-table tbody');
  tbody.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    appendCell(tr, `${row.window_label || windowKey} · 시나리오`);
    appendCell(tr, row.factor, { strong: row.factor === factor });
    appendCell(tr, `${formatPercent(row.period_return)}${row.raw_period_return != null ? ` · 원자료(저장값) ${formatPercent(row.raw_period_return)}` : ''}`, { className: classForNumber(row.period_return) });
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
  if (!state.data) return;
  renderSummary();
  renderDiagnostics();
  renderSelectedFactorMethod();
  renderFactorReturnChart();
  renderBacktestChart();
  renderWindowComparisonChart();
  renderLeaderTrendChart();
  renderWeightChart();
  renderEnsembleWeightChart();
  renderCurrentOutputTable();
  renderFactorTable();
  renderHoldingsTable();
  renderDailyWeightsAnalysis();
  renderPeriodRankingTable();
}

function renderWithBusy(message = '선택값을 반영하는 중입니다...') {
  if (!state.data) {
    setStatusMessage('데이터를 불러오는 중입니다. 입력값은 데이터 로딩 후 반영됩니다.');
    return;
  }
  setStatusMessage(message);
  window.setTimeout(() => {
    renderAll();
  }, 160);
}

bindManualUpdateControls();

if (typeof document.querySelectorAll === 'function') {
  document.querySelectorAll('[data-topn-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.querySelector('#topn-input');
      if (input) input.value = button.getAttribute('data-topn-preset') || DASHBOARD_INPUT_DEFAULTS.topN;
      renderWithBusy('상위 종목 수 프리셋을 반영하는 중입니다...');
    });
  });
  document.querySelectorAll('[data-max-weight-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.querySelector('#max-weight-input');
      if (input) input.value = button.getAttribute('data-max-weight-preset') || DASHBOARD_INPUT_DEFAULTS.maxWeightPercent;
      renderWithBusy('최대 비중 프리셋을 반영하는 중입니다...');
    });
  });
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
      state.hasUserSelectedFactor = false;
      fillControls();
      renderWithBusy('실행 결과를 전환하는 중입니다...');
    });
    document.querySelector('#factor-select').addEventListener('change', () => {
      state.hasUserSelectedFactor = true;
      fillDateOptions(currentRun(), selectedDate());
      renderWithBusy('선택 팩터를 반영하는 중입니다...');
    });
    ['#date-select', '#window-select'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => {
        syncDefaultFactorToCurrentBasis();
        renderWithBusy('기준일·기간의 최고 팩터를 반영하는 중입니다...');
      });
      document.querySelector(selector).addEventListener('change', () => {
        syncDefaultFactorToCurrentBasis();
        renderWithBusy('기준일·기간의 최고 팩터를 반영하는 중입니다...');
      });
    });
    ['#lookback-months-select', '#topn-input', '#max-weight-input', '#rebalance-select', '#transaction-cost-input', '#slippage-input'].forEach((selector) => {
      document.querySelector(selector).addEventListener('input', () => renderWithBusy('선택값을 반영하는 중입니다...'));
      document.querySelector(selector).addEventListener('change', () => renderWithBusy('선택값을 반영하는 중입니다...'));
    });
  })
  .catch((error) => {
    document.querySelector('#run-status').textContent = `대시보드 데이터를 불러오지 못했습니다: ${error}`;
  });
"""


def _score_columns(result: RunResult) -> list[str]:
    if not getattr(result, "factor_scores", None):
        return []
    columns: list[str] = []
    for scores in result.factor_scores.values():
        for column in scores.columns:
            if column not in columns:
                columns.append(column)
    return columns


def _score_eligibility_mask(result: RunResult) -> pd.DataFrame | None:
    columns = _score_columns(result)
    prices = getattr(result.market_data, "prices", pd.DataFrame())
    volumes = getattr(result.market_data, "volumes", pd.DataFrame())
    if not columns or prices is None or prices.empty:
        return None
    reference_index = next(iter(result.factor_scores.values())).index
    price_frame = prices.reindex(index=reference_index, columns=columns)
    if volumes is None or volumes.empty:
        volume_frame = pd.DataFrame(index=reference_index, columns=columns, dtype=float)
    else:
        volume_frame = volumes.reindex(index=reference_index, columns=columns)
    return build_eligibility_mask(price_frame, volume_frame, result.config)


def _eligibility_row(mask: pd.DataFrame | None, date: pd.Timestamp, symbols: pd.Index) -> pd.Series:
    if mask is None or mask.empty or date not in mask.index:
        return pd.Series(pd.NA, index=symbols, dtype="object")
    return mask.loc[date].reindex(symbols).fillna(False).astype(bool)

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
        eligibility_mask=_score_eligibility_mask(result),
    )
    weight_snapshots = _factor_weight_snapshots(
        result,
        period_matrix,
        max_snapshot_dates=max_score_snapshot_dates,
        max_symbols=max_score_snapshot_symbols,
        max_factors_per_period=10,
    )
    backtest_series = _factor_backtest_series(
        result,
        max_points=max_backtest_points,
    )
    benchmark_series = _benchmark_backtest_series(
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
            "factor_weight_snapshots": weight_snapshots,
            "scenario_available_dates": sorted(
                {row["date"] for row in score_snapshots if isinstance(row, dict) and row.get("date")},
                reverse=True,
            ),
            "scenario_available_dates_by_factor": _scenario_available_dates_by_factor(score_snapshots),
            "factor_backtest_series": backtest_series,
            "benchmark_backtest_series": benchmark_series,
            "latest_output_rows": latest_recommendations,
            "data_quality_summary": _data_quality_summary(result),
            "tradability_gate": _tradability_gate_rows(result.metadata),
            "factor_diagnostics": _factor_diagnostics_payload(result),
            "notes_ko": [
                "웹사이트 입력값은 브라우저 표시용이며 수동 실행 설정을 저장하지 않습니다.",
                "검토된 수동 실행 입력값은 .github/momentum-dashboard-config.json에서 관리합니다.",
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
    common_css_path = assets_dir / "common-ui.css"
    common_js_path = assets_dir / "common-ui.js"
    data_path = data_dir / "dashboard.json"
    summary_path = data_dir / "summary.json"

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
    index_path.write_text(HTML_TEMPLATE.format(title=escaped_title, asset_version=ASSET_VERSION), encoding="utf-8")
    css_path.write_text(CSS_CONTENT, encoding="utf-8")
    js_path.write_text(JS_CONTENT, encoding="utf-8")
    common_source_dir = Path(__file__).resolve().parents[1] / "docs" / "assets"
    common_css_path.write_text((common_source_dir / "common-ui.css").read_text(encoding="utf-8"), encoding="utf-8")
    common_js_path.write_text((common_source_dir / "common-ui.js").read_text(encoding="utf-8"), encoding="utf-8")
    data_path.write_text(
        json.dumps(combined, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(build_public_summary(combined), ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )

    return {
        "index": str(index_path),
        "css": str(css_path),
        "js": str(js_path),
        "common_css": str(common_css_path),
        "common_js": str(common_js_path),
        "data": str(data_path),
        "summary": str(summary_path),
    }


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def build_public_summary(combined_payload: dict[str, Any]) -> dict[str, Any]:
    """Build the compact cross-project summary consumed by quant-dashboard."""

    runs = combined_payload.get("runs") if isinstance(combined_payload.get("runs"), list) else []
    latest_index = combined_payload.get("latest_run_index")
    if not isinstance(latest_index, int) or latest_index < 0 or latest_index >= len(runs):
        latest_index = len(runs) - 1
    latest = runs[latest_index] if runs else {}
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    quality = latest.get("data_quality_summary") if isinstance(latest.get("data_quality_summary"), dict) else {}
    tradability_gate = latest.get("tradability_gate") if isinstance(latest.get("tradability_gate"), list) else []
    output_rows = latest.get("latest_output_rows") if isinstance(latest.get("latest_output_rows"), list) else []
    if not output_rows and isinstance(latest.get("holdings"), list):
        output_rows = latest.get("holdings")
    blockers = summary.get("tradability_blockers")
    if not isinstance(blockers, list):
        blockers = []
    state = "degraded" if summary.get("fail_closed") or summary.get("research_only") or blockers else "ok"
    data_as_of = summary.get("data_as_of") or summary.get("run_timestamp_utc")
    primary_entities = []
    for row in output_rows[:30]:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol") or row.get("ticker")
        if not symbol:
            continue
        primary_entities.append(
            {
                "symbol": symbol,
                "name": symbol,
                "label": f"{symbol} · rank {row.get('rank', len(primary_entities) + 1)}",
                "sector": "US Equity Momentum",
                "sectorLabel": "미국 주식 모멘텀",
                "themes": ["Momentum", "Factor", str(summary.get("selected_factor") or "")],
                "metrics": {
                    "rank": row.get("rank"),
                    "signal": row.get("signal") if row.get("signal") is not None else row.get("score"),
                    "displayWeight": _first_not_none(
                        row.get("display_weight"),
                        row.get("displayWeight"),
                        row.get("proposed_weight"),
                        row.get("pre_cap_weight"),
                        row.get("default_weight"),
                    ),
                    "finalWeight": _first_not_none(row.get("final_weight"), row.get("weight"), row.get("default_weight")),
                    "factor": row.get("selected_factor") or row.get("factor") or summary.get("selected_factor"),
                    "dataAsOf": data_as_of,
                },
                "signals": ["모멘텀 신호는 research-only 점검 출발점이며 매매 지시가 아닙니다."],
                "warnings": list(blockers[:3]) or ["tradability gate를 원본에서 확인하세요."],
            }
        )
    return {
        "schemaVersion": 1,
        "contract": "quant-research-summary",
        "projectId": "momentum",
        "projectName": "모멘텀 팩터 랩",
        "generatedAt": combined_payload.get("generated_at_utc"),
        "dataAsOf": data_as_of,
        "timezone": "UTC",
        "detailUrl": "https://sonchanggi.github.io/momentum-factor-lab/",
        "detailDataUrl": "https://sonchanggi.github.io/momentum-factor-lab/data/dashboard.json",
        "status": {
            "state": state,
            "label": summary.get("recommendation_output_label") or "Research signals",
            "cadence": "scheduled 06:30 KST Tue-Sat with 08:30/10:30/12:30 KST freshness-gated watchdog fallbacks; workflow_dispatch on demand",
            "expectedFreshnessDays": 7,
            "degradedReasons": [str(item) for item in blockers],
        },
        "coverage": {
            "runCount": len(runs),
            "candidateUniverseSize": summary.get("candidate_universe_size"),
            "eligiblePriceUniverseSize": summary.get("eligible_price_universe_size"),
            "liquidityEligibleUniverseSize": summary.get("liquidity_eligible_universe_size"),
            "factorCount": summary.get("factor_count"),
            "quality": quality,
        },
        "highlights": [
            {"label": "Selected factor", "value": summary.get("selected_factor"), "description": summary.get("selected_reason")},
            {"label": "Output", "value": summary.get("recommendation_output_label"), "description": "fail-closed일 때 zero-weight research signals"},
            {"label": "Blockers", "value": len(blockers), "description": "tradability gate blockers"},
        ],
        "primaryEntities": primary_entities,
        "limitations": [
            "Signals are research-only unless every tradability requirement passes.",
            "Fail-closed output uses zero final weights when practical tradability is not proven.",
            "Point-in-time universe, complete price coverage, liquidity, and same-sample selection checks must be reviewed.",
        ],
        "sources": [
            {"label": "Yahoo/yfinance free public data", "url": "https://finance.yahoo.com/"},
        ],
        "automation": {
            "workflowUrl": "https://github.com/SonChangGi/momentum-factor-lab/actions/workflows/daily-dashboard.yml",
            "manualUpdateLabel": "GitHub Actions daily-dashboard 수동 실행 / scheduled refresh",
            "tokenPolicy": "Static page keeps no GitHub token.",
        },
        "payload": {
            "summaryBytes": None,
            "detailBytes": combined_payload.get("payload_limits", {}).get("actual_json_bytes")
            if isinstance(combined_payload.get("payload_limits"), dict)
            else None,
        },
    }


def _dashboard_summary(result: RunResult) -> dict[str, Any]:
    summary = {
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
        "chart_benchmark": result.config.chart_benchmark,
        "chart_benchmark_symbol": result.metadata.get("chart_benchmark_symbol"),
        "chart_benchmark_price_available": result.metadata.get("chart_benchmark_price_available"),
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
    return _copy_summary_safety_fields(summary, result.metadata)


DASHBOARD_SUMMARY_SAFETY_KEYS: tuple[str, ...] = (
    "recommendation_output_key",
    "recommendation_output_label",
    "recommendation_output_sheet",
    "recommendation_output_available",
    "tradable_output_available",
    "current_recommendations_available",
    "tradable_recommendations_available",
    "fresh_live_data_available",
    "research_only",
    "decision_support_tier",
    "fail_closed",
    "fail_closed_reasons",
    "tradability_blockers",
    "execution_limitations",
    "tradability_requirements",
    "validation_selected_factor",
    "selected_factor_selection_source",
    "same_run_factor_selection_blocked_for_tradable",
    "same_sample_selection_blocked_for_tradable",
    "factor_selection_warning",
    "selection_policy_frozen_for_live",
    "frozen_policy_status",
    "frozen_policy_id",
    "frozen_policy_sha256",
    "frozen_policy_created_at_utc",
    "frozen_policy_effective_from",
    "frozen_policy_checks",
    "recommendation_weighting_method",
    "recommendation_weight_sum",
    "recommendation_cash_weight",
    "chart_benchmark_symbol",
    "chart_benchmark_price_available",
)


def _copy_summary_safety_fields(summary: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep dashboard summaries self-describing about research vs practical output."""

    for key in DASHBOARD_SUMMARY_SAFETY_KEYS:
        if key in metadata:
            summary[key] = metadata.get(key)
    return summary


DASHBOARD_RESEARCH_ONLY_SELECTION_SOURCES = frozenset(
    {"research_validation", "walk_forward", "walk_forward_insufficient_history"}
)
DASHBOARD_RESEARCH_ONLY_ZERO_FIELDS = (
    "weight",
    "proposed_weight",
    "target_notional",
    "adv_participation",
    "capacity_utilization",
    "capacity_aum_limit",
)


def _first_output_row_value(rows: list[Any], key: str) -> Any:
    for row in rows:
        if isinstance(row, dict) and row.get(key) is not None:
            return row.get(key)
    return None


def _append_unique(values: Any, *items: str) -> list[str]:
    result: list[str] = []
    if isinstance(values, list):
        result.extend(str(value) for value in values)
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _remove_items(values: Any, *items: str) -> list[str]:
    blocked = set(items)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value) not in blocked]


def _dashboard_factor_selection_policy_available(
    summary: dict[str, Any],
    rows: list[Any],
    selection_source: Any,
) -> bool:
    row_sources = {
        str(row.get("selected_factor_selection_source"))
        for row in rows
        if isinstance(row, dict) and row.get("selected_factor_selection_source") is not None
    }
    source = str(selection_source) if selection_source is not None else None
    if source == "predeclared" or row_sources == {"predeclared"}:
        return (
            summary.get("selection_policy_frozen_for_live") is True
        ) and summary.get("same_run_factor_selection_blocked_for_tradable") is not True
    requirements = summary.get("tradability_requirements")
    return bool(isinstance(requirements, dict) and requirements.get("factor_selection_policy_available") is True)


def _dashboard_no_same_sample_factor_selection(
    summary: dict[str, Any],
    rows: list[Any],
    selection_source: Any,
) -> bool:
    if summary.get("same_run_factor_selection_blocked_for_tradable") is True:
        return False
    if summary.get("same_sample_selection_blocked_for_tradable") is True:
        return False
    if _dashboard_factor_selection_policy_available(summary, rows, selection_source):
        return True
    requirements = summary.get("tradability_requirements")
    return bool(isinstance(requirements, dict) and requirements.get("no_same_sample_factor_selection") is True)


def _dashboard_rows_are_research_only(summary: dict[str, Any], rows: list[Any]) -> bool:
    if any(
        isinstance(row, dict)
        and (
            row.get("recommendation_output") == "research_signals"
            or row.get("selected_factor_selection_source") in DASHBOARD_RESEARCH_ONLY_SELECTION_SOURCES
        )
        for row in rows
    ):
        return True
    return not _dashboard_has_affirmative_practical_proof(summary)


def _dashboard_has_affirmative_practical_proof(summary: dict[str, Any]) -> bool:
    return (
        summary.get("recommendation_output_key") == "recommendations"
        and summary.get("research_only") is False
        and summary.get("recommendation_output_available") is True
        and summary.get("tradable_output_available") is True
        and summary.get("current_recommendations_available") is True
        and summary.get("tradable_recommendations_available") is True
        and summary.get("same_run_factor_selection_blocked_for_tradable") is False
        and summary.get("same_sample_selection_blocked_for_tradable") is False
        and summary.get("selected_factor_selection_source") == "predeclared"
    )


def _restore_pre_cap_weight_from_raw_scores(rows: list[dict[str, Any]]) -> None:
    raw_scores: list[float | None] = []
    for row in rows:
        raw = row.get("raw_weight_score")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raw_scores.append(None)
            continue
        raw_scores.append(value if value > 0 else None)
    total = sum(value for value in raw_scores if value is not None)
    if total <= 0:
        return
    for row, value in zip(rows, raw_scores, strict=False):
        if value is None:
            continue
        existing = row.get("pre_cap_weight")
        try:
            existing_value = float(existing)
        except (TypeError, ValueError):
            existing_value = 0.0
        if existing_value <= 0:
            row["pre_cap_weight"] = value / total


def _sanitize_research_only_output_rows(rows: list[Any], summary: dict[str, Any]) -> list[Any]:
    if not _dashboard_rows_are_research_only(summary, rows):
        return rows
    reason = "; ".join(summary.get("tradability_blockers") or summary.get("fail_closed_reasons") or [])
    if not reason:
        reason = "research_only_or_non_tradable_output"
    dict_rows = [dict(row) for row in rows if isinstance(row, dict)]
    _restore_pre_cap_weight_from_raw_scores(dict_rows)
    sanitized: list[Any] = []
    restored_iter = iter(dict_rows)
    for row in rows:
        if not isinstance(row, dict):
            sanitized.append(row)
            continue
        clean = next(restored_iter)
        for key in DASHBOARD_RESEARCH_ONLY_ZERO_FIELDS:
            if key in clean:
                clean[key] = 0.0
        if "capacity_pass" in clean:
            clean["capacity_pass"] = False
        if clean.get("capacity_status") == "pass":
            clean["capacity_status"] = "research_only_gate_failed"
            if "capacity_warning" in clean:
                clean["capacity_warning"] = (
                    "연구용 fail-closed 출력입니다. 용량 점검 통과 여부와 무관하게 매매 권고가 아니며 "
                    f"미충족 요건은 {reason}입니다."
                )
        clean["tradable_weight_enabled"] = False
        clean.setdefault("research_only_reason", reason)
        sanitized.append(clean)
    return sanitized


def _sanitize_dashboard_payload_safety(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.setdefault("summary", {})
    if not isinstance(summary, dict):
        summary = {}
        payload["summary"] = summary
    rows = payload.get("latest_output_rows", [])
    if not isinstance(rows, list):
        rows = []
    research_only = _dashboard_rows_are_research_only(summary, rows)
    selection_source = summary.get("selected_factor_selection_source") or _first_output_row_value(
        rows,
        "selected_factor_selection_source",
    )
    if selection_source is not None:
        summary.setdefault("selected_factor_selection_source", selection_source)
    if research_only:
        factor_policy_available = _dashboard_factor_selection_policy_available(summary, rows, selection_source)
        no_same_sample_selection = _dashboard_no_same_sample_factor_selection(summary, rows, selection_source)
        summary["recommendation_output_key"] = "research_signals"
        summary["recommendation_output_label"] = "Research signals (not tradable)"
        summary["recommendation_output_available"] = False
        summary["tradable_output_available"] = False
        summary["current_recommendations_available"] = False
        summary["tradable_recommendations_available"] = False
        summary["research_only"] = True
        summary["decision_support_tier"] = "research_signals"
        summary["fail_closed"] = True
        if selection_source is None:
            summary.setdefault("selected_factor_selection_source", "unverified_legacy_or_missing_metadata")
        if factor_policy_available:
            summary["selected_factor_selection_source"] = "predeclared"
            summary["selection_policy_frozen_for_live"] = True
            summary["same_run_factor_selection_blocked_for_tradable"] = False
            summary["same_sample_selection_blocked_for_tradable"] = False
            if isinstance(summary.get("factor_selection_warning"), str):
                summary["factor_selection_warning"] = None
            summary["tradability_blockers"] = _remove_items(
                summary.get("tradability_blockers") or summary.get("fail_closed_reasons"),
                "factor_selection_policy_available",
                "no_same_sample_factor_selection",
            )
            summary["execution_limitations"] = _remove_items(
                summary.get("execution_limitations"),
                "factor_selection_policy_available",
                "no_same_sample_factor_selection",
            )
            summary["fail_closed_reasons"] = _remove_items(
                summary.get("fail_closed_reasons") or summary.get("tradability_blockers"),
                "factor_selection_policy_available",
                "no_same_sample_factor_selection",
            )
        else:
            summary["same_run_factor_selection_blocked_for_tradable"] = not no_same_sample_selection
            summary["same_sample_selection_blocked_for_tradable"] = not no_same_sample_selection
            summary["factor_selection_warning"] = (
                "사전 고정 팩터 정책 파일 검증이 없어 실전 매매 권고로 승격하지 않습니다."
                if no_same_sample_selection
                else (
                    "실전 출력임을 입증하는 안전 메타데이터가 없거나 같은 실행에서 고른 연구용 팩터입니다. "
                    "대시보드는 보수적으로 매매 권고가 아닌 연구용 신호로 처리합니다."
                )
            )
            if isinstance(summary.get("selected_reason"), str):
                summary["selected_reason"] = (
                    summary["selected_reason"]
                    .replace(
                        "use a predeclared selected factor or walk-forward selection for practical labels",
                        "use a predeclared selected factor frozen before the run for practical labels",
                    )
                    .replace(
                        "predeclare a selected factor or use walk-forward selection for practical labels",
                        "predeclare/freeze the selected factor before the run for practical labels",
                    )
                )
            selection_blockers = (
                ("factor_selection_policy_available",)
                if no_same_sample_selection
                else ("factor_selection_policy_available", "no_same_sample_factor_selection")
            )
            summary["tradability_blockers"] = _append_unique(
                summary.get("tradability_blockers") or summary.get("fail_closed_reasons"),
                *selection_blockers,
            )
            summary["execution_limitations"] = _append_unique(
                summary.get("execution_limitations"),
                *selection_blockers,
            )
            summary["fail_closed_reasons"] = _append_unique(
                summary.get("fail_closed_reasons") or summary.get("tradability_blockers"),
                *selection_blockers,
            )
        requirements = summary.setdefault("tradability_requirements", {})
        if isinstance(requirements, dict):
            requirements["factor_selection_policy_available"] = bool(factor_policy_available)
            requirements["no_same_sample_factor_selection"] = bool(no_same_sample_selection)
        payload["latest_output_rows"] = _sanitize_research_only_output_rows(rows, summary)
        data_quality = payload.get("data_quality_summary")
        if isinstance(data_quality, dict):
            row_count = len(payload["latest_output_rows"])
            if row_count:
                data_quality["capacity_status_counts"] = {"research_only_gate_failed": row_count}
    requirements = summary.get("tradability_requirements")
    if isinstance(requirements, dict) and requirements:
        payload["tradability_gate"] = _tradability_gate_rows(summary)
    return payload


GATE_LABELS_KO: dict[str, tuple[str, str]] = {
    "fresh_live_data": ("최신 실데이터", "전일/최근 미국 종가 데이터가 충분히 최신인지 확인합니다."),
    "factor_selection_policy_available": ("사전 고정된 팩터 선택 정책", "같은 실행의 검증/연구 순위로 고른 팩터를 매매 권고로 쓰지 않도록 막습니다."),
    "no_same_sample_factor_selection": ("동일 표본 팩터 선택 차단", "같은 실행·같은 표본에서 고른 연구용 팩터가 실전 추천으로 승격되지 않았는지 확인합니다."),
    "no_explicit_price_symbol_cap": ("가격 수집 범위 제한 없음", "디버그용 종목 수 제한이 걸린 실행인지 확인합니다."),
    "complete_requested_price_coverage": ("요청 종목 가격 수신", "요청한 후보 종목의 가격이 공급자에서 실제로 수신됐는지 확인합니다. 이후 이력·유동성·품질 필터는 별도 게이트에서 점검합니다."),
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


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        num = float(numerator)
        den = float(denominator)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(num) or not np.isfinite(den) or den <= 0:
        return None
    return num / den


def _numeric_group_series(group: pd.DataFrame, column: str) -> pd.Series:
    if column not in group.columns:
        return pd.Series(0.0, index=group.index, dtype=float)
    return pd.to_numeric(group[column], errors="coerce").fillna(0)


def _data_source_health_rows(data_sources: pd.DataFrame) -> list[dict[str, Any]]:
    if data_sources.empty or "source" not in data_sources:
        return []
    provider_order = {
        "yfinance-adjusted-daily": 0,
        "yahoo-chart-adjusted-daily-fallback": 1,
        "nasdaq-latest-close-repair": 2,
        "stooq-daily-close-fallback": 3,
        "finance-datareader-close-fallback": 4,
        "yfinance-fast-info-market-cap": 5,
        "finviz-snapshot-market-cap": 6,
        "live-run-summary": 7,
    }
    rows: list[dict[str, Any]] = []
    for source, group in data_sources.groupby("source", sort=False):
        source_text = str(source)
        records = _numeric_group_series(group, "records")
        statuses = group.get("status", pd.Series(index=group.index, dtype=object)).fillna("unknown").astype(str)
        requested = _numeric_group_series(group, "requested_price_symbols")
        returned = _numeric_group_series(group, "returned_price_symbols")
        failed_mask = statuses.str.contains("failed|unavailable|invalid", case=False, regex=True)
        no_newer_mask = statuses.eq("no_newer_rows")
        success_mask = records.gt(0)
        if not success_mask.any() and not failed_mask.any() and not no_newer_mask.any() and source_text not in provider_order:
            continue
        rows.append(
            {
                "source": source_text,
                "row_count": int(len(group)),
                "success_rows": int(success_mask.sum()),
                "failed_rows": int(failed_mask.sum()),
                "no_newer_rows": int(no_newer_mask.sum()),
                "cache_hit_rows": int(statuses.str.contains("cache_hit", case=False, regex=False).sum()),
                "records_sum": float(records.sum()),
                "requested_price_symbols_sum": float(requested.sum()) if requested.sum() else None,
                "returned_price_symbols_sum": float(returned.sum()) if returned.sum() else None,
            }
        )
    return sorted(rows, key=lambda row: (provider_order.get(str(row["source"]), 99), str(row["source"])))


def _provider_coverage_counts(data_sources: pd.DataFrame) -> tuple[float | None, float | None]:
    if data_sources.empty or "source" not in data_sources:
        return None, None
    summary_rows = data_sources[data_sources["source"].astype(str).eq("live-run-summary")]
    if summary_rows.empty:
        return None, None
    row = summary_rows.iloc[-1]
    requested = pd.to_numeric(pd.Series([row.get("requested_price_symbols")]), errors="coerce").iloc[0]
    returned = pd.to_numeric(pd.Series([row.get("returned_price_symbols")]), errors="coerce").iloc[0]
    requested_value = float(requested) if pd.notna(requested) else None
    returned_value = float(returned) if pd.notna(returned) else None
    return requested_value, returned_value


def _data_quality_summary_from_components(
    *,
    summary: dict[str, Any],
    data_sources: pd.DataFrame,
    data_quality: pd.DataFrame,
    price_sources: pd.DataFrame | None,
    stale_after_days: int,
) -> dict[str, Any]:
    source_counts = {}
    if not data_sources.empty and "source" in data_sources:
        source_counts = data_sources["source"].value_counts().to_dict()
    status_counts = {}
    if not data_quality.empty and "data_quality_status" in data_quality:
        status_counts = data_quality["data_quality_status"].value_counts().to_dict()
    price_source_counts = {}
    if isinstance(price_sources, pd.DataFrame) and not price_sources.empty and "price_source" in price_sources:
        price_source_counts = price_sources["price_source"].value_counts().to_dict()
    elif not data_quality.empty and "price_source" in data_quality:
        price_source_counts = data_quality["price_source"].value_counts().to_dict()
    candidate_count = summary.get("candidate_universe_size")
    fetched_count = summary.get("fetched_price_symbol_count")
    eligible_count = summary.get("eligible_price_universe_size")
    liquidity_count = summary.get("liquidity_eligible_universe_size")
    excluded_count = summary.get("excluded_symbols")
    provider_requested_count, provider_returned_count = _provider_coverage_counts(data_sources)
    if provider_requested_count is None:
        provider_requested_count = candidate_count
    if provider_returned_count is None:
        provider_returned_count = fetched_count
    quality_rows = len(data_quality) if not data_quality.empty else 0
    quality_pass_count = 0
    if not data_quality.empty and "data_quality_pass" in data_quality:
        quality_pass_count = int(data_quality["data_quality_pass"].fillna(False).astype(bool).sum())
    fresh_price_rows = None
    fresh_price_ratio = None
    if not data_quality.empty and "stale_days" in data_quality:
        stale_days = pd.to_numeric(data_quality["stale_days"], errors="coerce")
        fresh_price_rows = int(stale_days.le(stale_after_days).fillna(False).sum())
        fresh_price_ratio = _safe_ratio(fresh_price_rows, quality_rows)
    return {
        "candidate_universe_size": candidate_count,
        "eligible_price_universe_size": eligible_count,
        "liquidity_eligible_universe_size": liquidity_count,
        "fetched_price_symbol_count": fetched_count,
        "excluded_symbols": excluded_count,
        "provider": summary.get("provider"),
        "data_as_of": summary.get("data_as_of"),
        "provider_requested_symbol_count": provider_requested_count,
        "provider_returned_symbol_count": provider_returned_count,
        "price_coverage_ratio": _safe_ratio(provider_returned_count, provider_requested_count),
        "model_price_universe_ratio": _safe_ratio(fetched_count, candidate_count),
        "eligible_price_ratio": _safe_ratio(eligible_count, candidate_count),
        "liquidity_eligible_ratio": _safe_ratio(liquidity_count, candidate_count),
        "excluded_ratio": _safe_ratio(excluded_count, candidate_count),
        "price_quality_rows": quality_rows,
        "data_quality_pass_count": quality_pass_count,
        "data_quality_pass_ratio": _safe_ratio(quality_pass_count, quality_rows),
        "fresh_price_rows": fresh_price_rows,
        "fresh_price_ratio": fresh_price_ratio,
        "data_quality_status_counts": status_counts,
        "price_source_counts": price_source_counts,
        "source_counts": source_counts,
        "source_health": _data_source_health_rows(data_sources),
        "liquidity_status_counts": summary.get("recommendation_liquidity_status_counts", {}),
        "capacity_status_counts": summary.get("recommendation_capacity_status_counts", {}),
    }


def _data_quality_summary(result: RunResult) -> dict[str, Any]:
    price_sources = getattr(result, "price_sources", None)
    if price_sources is None and getattr(result, "market_data", None) is not None:
        price_sources = getattr(result.market_data, "price_sources", None)
    return _data_quality_summary_from_components(
        summary=result.metadata,
        data_sources=result.data_sources,
        data_quality=result.data_quality,
        price_sources=price_sources,
        stale_after_days=result.config.stale_after_days,
    )


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
    "asymmetry": "상승장 참여도와 하락장 방어력을 함께 보려는 비대칭 참여 계열입니다.",
    "tail_risk": "좌측 꼬리위험과 급락 민감도를 모멘텀에 반영하는 꼬리위험 보정 계열입니다.",
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
    eligibility_mask: pd.DataFrame | None = None,
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
            raw_scores = scores.loc[score_date].dropna()
            if raw_scores.empty:
                continue
            eligible = _eligibility_row(eligibility_mask, score_date, raw_scores.index)
            eligibility_available = not eligible.isna().all()
            if eligibility_available:
                ranked = raw_scores.where(eligible.astype(bool)).dropna().sort_values(ascending=False)
                score_scope = "eligible_current_model_portfolio"
            else:
                ranked = raw_scores.sort_values(ascending=False)
                score_scope = "raw_research_diagnostic_eligibility_not_available"
            if ranked.empty:
                continue
            top = ranked.head(max_symbols)
            snapshots.append(
                {
                    "date": date_text,
                    "factor": str(factor),
                    "score_date": _date_str(score_date),
                    "available_count": int(ranked.size),
                    "raw_available_count": int(raw_scores.size),
                    "eligibility_filter_applied": bool(eligibility_available),
                    "score_scope": score_scope,
                    "rows": [[str(symbol), _rounded_float(score)] for symbol, score in top.items()],
                }
            )
    return snapshots


def _factor_weight_snapshots(
    result: RunResult,
    period_matrix: list[dict[str, Any]],
    *,
    max_snapshot_dates: int,
    max_symbols: int,
    max_factors_per_period: int,
) -> list[dict[str, Any]]:
    """Export active backtest holding weights for top factors by date/window.

    These rows are intentionally separate from factor-score snapshots. Score
    snapshots power the user-selected-factor browser scenario, while weight
    snapshots preserve each factor portfolio's existing backtest allocation for
    cross-factor ensemble diagnostics.
    """

    if not period_matrix or not result.backtests:
        return []
    dates = sorted({row["date"] for row in period_matrix if row.get("date")})[-max_snapshot_dates:]
    score_indexes = {
        factor: pd.DatetimeIndex(scores.index)
        for factor, scores in result.factor_scores.items()
        if not scores.empty
    }
    snapshots: list[dict[str, Any]] = []
    for matrix_row in period_matrix:
        date_text = matrix_row.get("date")
        if date_text not in dates:
            continue
        factors = matrix_row.get("factors")
        if not isinstance(factors, list) or not factors:
            continue
        returns = matrix_row.get("returns") if isinstance(matrix_row.get("returns"), list) else []
        requested_date = pd.Timestamp(date_text)
        for rank, factor in enumerate(factors[:max_factors_per_period], start=1):
            factor_name = str(factor)
            backtest = result.backtests.get(factor_name)
            if backtest is None or backtest.weights.empty:
                continue
            weight_frame = backtest.weights
            weight_index = pd.DatetimeIndex(weight_frame.index)
            weight_date = _nearest_score_date(weight_index, requested_date)
            if weight_date is None:
                continue
            weights = pd.to_numeric(weight_frame.loc[weight_date], errors="coerce").dropna()
            active_weights = weights[weights > 1e-12].sort_values(ascending=False)
            if active_weights.empty:
                continue
            score_index = score_indexes.get(factor_name)
            score_date = _active_signal_date(backtest, weight_date, score_index) if score_index is not None else None
            row_scores = pd.Series(dtype=float)
            scores = result.factor_scores.get(factor_name)
            if scores is not None and not scores.empty and score_date is not None and score_date in scores.index:
                row_scores = pd.to_numeric(scores.loc[score_date], errors="coerce")
            top_weights = active_weights.head(max_symbols)
            rows = [
                [
                    str(symbol),
                    _rounded_float(weight, digits=8),
                    _rounded_float(row_scores.get(symbol), digits=6) if not row_scores.empty else None,
                ]
                for symbol, weight in top_weights.items()
            ]
            snapshots.append(
                {
                    "date": str(date_text),
                    "window": str(matrix_row.get("window") or ""),
                    "window_label": str(matrix_row.get("window_label") or matrix_row.get("window") or ""),
                    "factor": factor_name,
                    "factor_rank": rank,
                    "period_return": _float_or_none(returns[rank - 1]) if rank - 1 < len(returns) else None,
                    "weight_date": _date_str(weight_date),
                    "score_date": _date_str(score_date) if score_date is not None else None,
                    "available_count": int(active_weights.size),
                    "exported_count": int(len(rows)),
                    "weight_source": "백테스트 일별 보유 비중",
                    "rows": rows,
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


def _benchmark_backtest_series(result: RunResult, *, max_points: int) -> dict[str, Any]:
    symbol = normalize_symbol(result.config.chart_benchmark)
    prices = result.market_data.prices.dropna(axis=1, how="all")
    column = next((column for column in prices.columns if normalize_symbol(column) == symbol), None)
    if column is None:
        return {
            "symbol": symbol,
            "label_ko": _benchmark_label_ko(symbol),
            "dates": [],
            "equity": [],
            "drawdown": [],
        }
    price_series = pd.to_numeric(prices[column], errors="coerce").dropna().sort_index()
    if price_series.empty:
        return {
            "symbol": symbol,
            "label_ko": _benchmark_label_ko(symbol),
            "dates": [],
            "equity": [],
            "drawdown": [],
        }
    equity = price_series.divide(float(price_series.iloc[0]))
    drawdown = equity.divide(equity.cummax()).subtract(1.0)
    if len(equity) > max_points:
        equity = equity.tail(max_points)
        drawdown = drawdown.reindex(equity.index)
    return {
        "symbol": symbol,
        "label_ko": _benchmark_label_ko(symbol),
        "dates": [_date_str(date) for date in equity.index],
        "equity": [_rounded_float(value) for value in equity.values],
        "drawdown": [_rounded_float(drawdown.loc[date]) for date in equity.index],
    }


def _benchmark_label_ko(symbol: str) -> str:
    labels = {
        "QQQ": "나스닥-100(QQQ)",
        "IXIC": "나스닥 종합지수",
        "^IXIC": "나스닥 종합지수",
        "SPY": "S&P 500(SPY)",
    }
    return labels.get(symbol, f"벤치마크 {symbol}")


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
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        config = payload.get("config", {}) if isinstance(payload.get("config"), dict) else {}
        summary = dashboard.setdefault("summary", {})
        if not isinstance(summary, dict):
            summary = {}
            dashboard["summary"] = summary
        _copy_summary_safety_fields(summary, metadata)
        if isinstance(payload.get("data_quality"), list) and isinstance(payload.get("data_sources"), list):
            dashboard["data_quality_summary"] = _data_quality_summary_from_components(
                summary=metadata,
                data_sources=pd.DataFrame(payload.get("data_sources") or []),
                data_quality=pd.DataFrame(payload.get("data_quality") or []),
                price_sources=pd.DataFrame(payload.get("price_sources") or []),
                stale_after_days=int(config.get("stale_after_days") or 7),
            )
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
        return _fit_dashboard_payload(
            _sanitize_dashboard_payload_safety(dashboard),
            max_bytes=DASHBOARD_PAYLOAD_MAX_BYTES,
        )
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
    legacy_payload = {
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
        "benchmark_backtest_series": [],
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
    return _json_safe(_sanitize_dashboard_payload_safety(legacy_payload))


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

    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    selected_factor = summary.get("selected_factor")
    factor_options = [
        option
        for option in payload.get("factor_options", [])
        if isinstance(option, dict) and option.get("factor") == selected_factor
    ][:1]
    if not factor_options:
        factor_options = list(payload.get("factor_options", []))[:1]
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
            "summary": summary,
            "periods": payload.get("periods", []),
            "factor_options": factor_options,
            "factor_leaders": list(payload.get("factor_leaders", []))[-60:],
            "factor_period_rankings": list(payload.get("factor_period_rankings", []))[-60:],
            "factor_period_matrix": [],
            "holdings": [],
            "factor_score_snapshots": [],
            "scenario_available_dates": [],
            "scenario_available_dates_by_factor": {},
            "factor_backtest_series": [],
            "benchmark_backtest_series": {},
            "latest_output_rows": [],
            "data_quality_summary": payload.get("data_quality_summary", {}),
            "tradability_gate": payload.get("tradability_gate", []),
            "factor_diagnostics": payload.get("factor_diagnostics", {}),
            "notes_ko": _unique_text_list(
                payload.get("notes_ko", []),
                "과거 실행은 compact 요약으로 보관되어 상세 보유 비중 표시는 최신 실행에 한정됩니다.",
            ),
        }
    )




def _unique_text_list(values: Any, *extra: str) -> list[str]:
    result: list[str] = []
    candidates = values if isinstance(values, list) else []
    for value in [*candidates, *extra]:
        text = str(value) if value is not None else ""
        if text and text not in result:
            result.append(text)
    return result

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


def _thin_line_series(series: dict[str, Any], *, minimum_points: int = 80) -> bool:
    dates = series.get("dates") or []
    if len(dates) <= minimum_points:
        return False
    indexes = list(range(len(dates)))[::2]
    if indexes[-1] != len(dates) - 1:
        indexes.append(len(dates) - 1)
    for key in ["dates", "equity", "drawdown"]:
        values = series.get(key) or []
        series[key] = [values[index] for index in indexes if index < len(values)]
    return True


def _snapshot_dates(payload: dict[str, Any], *, keys: tuple[str, ...]) -> list[str]:
    return sorted(
        {
            str(row.get("date"))
            for key in keys
            for row in payload.get(key, [])
            if isinstance(row, dict) and row.get("date")
        }
    )


def _protected_snapshot_dates(payload: dict[str, Any]) -> set[str]:
    score_dates = _snapshot_dates(payload, keys=("factor_score_snapshots",))
    protected = set(score_dates[-MIN_SCENARIO_SNAPSHOT_DATES:])
    weight_dates = _snapshot_dates(payload, keys=("factor_weight_snapshots",))
    protected.update(weight_dates[-MIN_SCENARIO_SNAPSHOT_DATES:])
    return protected


def _drop_oldest_unprotected_snapshot_date(payload: dict[str, Any], *, protected_dates: set[str]) -> bool:
    dates = [
        date
        for date in _snapshot_dates(payload, keys=("factor_score_snapshots", "factor_weight_snapshots"))
        if date not in protected_dates
    ]
    if not dates:
        return False
    oldest = dates[0]
    changed = False
    for key in ("factor_score_snapshots", "factor_weight_snapshots"):
        rows = payload.get(key, [])
        if not isinstance(rows, list):
            continue
        next_rows = [row for row in rows if not (isinstance(row, dict) and row.get("date") == oldest)]
        changed = changed or len(next_rows) != len(rows)
        payload[key] = next_rows
    return changed


def _thin_snapshot_rows(payload: dict[str, Any], *, minimum_symbols: int = MIN_SCENARIO_SNAPSHOT_SYMBOLS) -> bool:
    changed = False
    for key in ("factor_score_snapshots", "factor_weight_snapshots"):
        for snapshot in payload.get(key, []):
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
                continue
            rows = snapshot["rows"]
            if len(rows) <= minimum_symbols:
                continue
            target = max(minimum_symbols, (len(rows) + 1) // 2)
            snapshot["rows"] = rows[:target]
            if key == "factor_weight_snapshots":
                snapshot["exported_count"] = min(int(snapshot.get("exported_count") or len(rows)), target)
            changed = True
    return changed


def _ensure_latest_output_score_snapshot(payload: dict[str, Any]) -> None:
    if payload.get("factor_score_snapshots"):
        return
    rows = payload.get("latest_output_rows")
    if not isinstance(rows, list) or not rows:
        return
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    selected_factor = summary.get("selected_factor")
    if not selected_factor:
        for row in rows:
            if isinstance(row, dict) and row.get("selected_factor"):
                selected_factor = row.get("selected_factor")
                break
    if not selected_factor:
        return
    data_as_of = str(summary.get("data_as_of") or "")[:10]
    signal_date = data_as_of
    recovered_rows: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        if row.get("selected_factor") and str(row.get("selected_factor")) != str(selected_factor):
            continue
        if row.get("signal_date") and not signal_date:
            signal_date = str(row.get("signal_date"))[:10]
        score = _rounded_float(row.get("score"))
        if score is None:
            continue
        recovered_rows.append([str(row.get("symbol")), score])
    if not recovered_rows:
        return
    snapshot_date = data_as_of or signal_date
    if not snapshot_date:
        return
    payload["factor_score_snapshots"] = [
        {
            "date": snapshot_date,
            "factor": str(selected_factor),
            "score_date": signal_date or snapshot_date,
            "available_count": len(recovered_rows),
            "raw_available_count": len(recovered_rows),
            "eligibility_filter_applied": True,
            "score_scope": "latest_output_rows_recovery_partial",
            "rows": recovered_rows[:MAX_SCORE_SNAPSHOT_SYMBOLS],
        }
    ]
    payload["notes_ko"] = _unique_text_list(
        payload.get("notes_ko", []),
        "점수 스냅샷이 비어 있던 실행은 latest_output_rows에서 선택 팩터의 제한적 종목 스냅샷을 복구했습니다.",
    )


def _fit_dashboard_payload(payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    _ensure_latest_output_score_snapshot(payload)
    payload.setdefault("payload_limits", {})
    payload["payload_limits"].update(
        {
            "max_payload_bytes": max_bytes,
            "max_score_snapshot_symbols": MAX_SCORE_SNAPSHOT_SYMBOLS,
            "max_weight_snapshot_symbols": MAX_SCORE_SNAPSHOT_SYMBOLS,
            "max_backtest_points": MAX_BACKTEST_POINTS,
            "min_scenario_snapshot_dates": MIN_SCENARIO_SNAPSHOT_DATES,
            "min_scenario_snapshot_symbols": MIN_SCENARIO_SNAPSHOT_SYMBOLS,
            "snapshot_trim_policy": "최신 점수/비중 스냅샷 최소 1일치를 보존하고 오래된 날짜, 라인 포인트, 행 수 순서로 줄입니다.",
        }
    )
    protected_snapshot_dates = _protected_snapshot_dates(payload)
    while _json_payload_size(payload) > max_bytes and (
        payload.get("factor_score_snapshots") or payload.get("factor_weight_snapshots")
    ):
        if not _drop_oldest_unprotected_snapshot_date(payload, protected_dates=protected_snapshot_dates):
            break
    while _json_payload_size(payload) > max_bytes and payload.get("factor_backtest_series"):
        changed = False
        for series in payload["factor_backtest_series"]:
            changed = _thin_line_series(series) or changed
        benchmark_series = payload.get("benchmark_backtest_series")
        if isinstance(benchmark_series, dict):
            changed = _thin_line_series(benchmark_series) or changed
        if not changed:
            break
    while _json_payload_size(payload) > max_bytes and _thin_snapshot_rows(payload):
        pass
    payload["scenario_available_dates"] = sorted(
        {row.get("date") for row in payload.get("factor_score_snapshots", []) if row.get("date")},
        reverse=True,
    )
    payload["scenario_available_dates_by_factor"] = _scenario_available_dates_by_factor(
        [row for row in payload.get("factor_score_snapshots", []) if isinstance(row, dict)]
    )
    payload["payload_limits"]["actual_payload_bytes"] = _json_payload_size(payload)
    payload["payload_limits"]["score_snapshot_dates_exported"] = len(payload["scenario_available_dates"])
    payload["payload_limits"]["weight_snapshot_dates_exported"] = len(
        {row.get("date") for row in payload.get("factor_weight_snapshots", []) if row.get("date")}
    )
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
