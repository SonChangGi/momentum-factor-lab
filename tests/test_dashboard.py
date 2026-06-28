import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from momentum_factor_lab import cli
from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.dashboard import (
    ASSET_VERSION,
    CSS_CONTENT,
    HTML_TEMPLATE,
    JS_CONTENT,
    _factor_score_snapshots,
    _fit_dashboard_payload,
    _holding_rows,
    _json_payload_size,
    build_dashboard_payload,
    build_public_summary,
    write_dashboard_site,
)
from momentum_factor_lab.report import write_reports
from momentum_factor_lab.workflow import run_analysis


def test_dashboard_payload_contains_period_leaders_and_holdings(tmp_path):
    result = run_analysis(
        RunConfig(
            start_date="2019-01-01",
            output_dir=tmp_path / "outputs",
            report_dir=tmp_path / "reports",
            offline_sample=True,
            top_n=5,
            max_weight=0.2,
        )
    )

    payload = build_dashboard_payload(result, max_history_days=20, max_holdings_per_period=10)

    assert payload["schema_version"] == 1
    assert {period["key"] for period in payload["periods"]} == {"1M", "3M", "6M", "1Y"}
    assert payload["summary"]["selected_factor"] == result.selected_factor
    assert payload["factor_options"]
    assert payload["factor_options"][0]["description_ko"]
    assert payload["factor_leaders"]
    assert {"date", "window", "best_factor", "best_return"}.issubset(payload["factor_leaders"][0])
    assert payload["factor_period_matrix"]
    assert {"date", "window", "factors", "returns"}.issubset(payload["factor_period_matrix"][0])
    assert payload["factor_score_snapshots"]
    assert {"date", "factor", "score_date", "rows"}.issubset(payload["factor_score_snapshots"][0])
    assert payload["factor_weight_snapshots"]
    assert {"date", "window", "factor", "weight_date", "rows"}.issubset(payload["factor_weight_snapshots"][0])
    assert payload["factor_backtest_series"]
    assert {"factor", "dates", "equity", "drawdown"}.issubset(payload["factor_backtest_series"][0])
    assert payload["benchmark_backtest_series"]["symbol"] == "^IXIC"
    assert payload["benchmark_backtest_series"]["label_ko"] == "나스닥 종합지수"
    assert payload["benchmark_backtest_series"]["dates"]
    assert payload["holdings"]
    assert {"symbol", "score", "default_weight", "window", "weight_source"}.issubset(payload["holdings"][0])
    assert payload["holdings"][0]["weight_source"] == "백테스트 일별 보유 비중"
    quality = payload["data_quality_summary"]
    assert quality["candidate_universe_size"] >= 2000
    assert quality["price_coverage_ratio"] is not None
    assert quality["eligible_price_ratio"] is not None
    assert quality["data_quality_pass_ratio"] is not None
    assert quality["source_health"]
    assert {"source", "success_rows", "failed_rows", "records_sum"}.issubset(quality["source_health"][0])
    assert payload["tradability_gate"]
    assert {"key", "label_ko", "description_ko", "passed"}.issubset(payload["tradability_gate"][0])
    assert payload["factor_diagnostics"]["category_summary"]
    assert payload["factor_diagnostics"]["rank_ic_top"]
    assert payload["factor_diagnostics"]["redundancy_top"]
    assert payload["notes_ko"][0].startswith("웹사이트 입력값")
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) < 5_000_000


def test_holding_rows_use_active_backtest_weights_and_signal_date():
    scores = pd.DataFrame(
        {
            "AAA": [10.0, 1.0],
            "BBB": [9.0, 2.0],
            "CCC": [1.0, 99.0],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-10"]),
    )
    weights = pd.DataFrame(
        {"AAA": [0.61], "BBB": [0.39], "CCC": [0.0]},
        index=pd.to_datetime(["2026-01-10"]),
    )
    backtest = SimpleNamespace(
        weights=weights,
        signal_dates=pd.Series(
            [pd.Timestamp("2026-01-01")],
            index=pd.to_datetime(["2026-01-05"]),
        ),
    )
    result = SimpleNamespace(
        factor_scores={"factor_a": scores},
        backtests={"factor_a": backtest},
    )
    leaders = [
        {
            "date": "2026-01-10",
            "window": "1M",
            "window_label": "최근 1개월",
            "best_factor": "factor_a",
        }
    ]

    rows = _holding_rows(result, leaders, max_holdings_per_period=3)

    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]
    assert [row["score_date"] for row in rows] == ["2026-01-01", "2026-01-01"]
    assert [row["default_weight"] for row in rows] == [0.61, 0.39]


def test_factor_score_snapshots_use_model_eligibility_for_scenario_rows():
    scores = pd.DataFrame(
        {
            "RAW_HIGH": [10.0],
            "ELIGIBLE": [8.0],
            "ALSO_OK": [5.0],
        },
        index=pd.to_datetime(["2026-01-10"]),
    )
    eligibility = pd.DataFrame(
        {
            "RAW_HIGH": [False],
            "ELIGIBLE": [True],
            "ALSO_OK": [True],
        },
        index=pd.to_datetime(["2026-01-10"]),
    )
    result = SimpleNamespace(factor_scores={"mom_test": scores})
    leaders = [
        {
            "date": "2026-01-10",
            "window": "1M",
            "window_label": "최근 1개월",
            "best_factor": "mom_test",
        }
    ]

    snapshots = _factor_score_snapshots(
        result,
        leaders,
        max_snapshot_dates=1,
        max_symbols=10,
        eligibility_mask=eligibility,
    )

    assert snapshots[0]["eligibility_filter_applied"] is True
    assert snapshots[0]["score_scope"] == "eligible_current_model_portfolio"
    assert snapshots[0]["available_count"] == 2
    assert snapshots[0]["raw_available_count"] == 3
    assert [row[0] for row in snapshots[0]["rows"]] == ["ELIGIBLE", "ALSO_OK"]


def test_payload_fit_preserves_latest_scenario_snapshots_under_size_pressure():
    dates = [f"2026-06-{day:02d}" for day in range(1, 5)]
    score_snapshots = []
    weight_snapshots = []
    for date_text in dates:
        for factor_index in range(12):
            score_snapshots.append(
                {
                    "date": date_text,
                    "factor": f"factor_{factor_index}",
                    "score_date": date_text,
                    "available_count": 30,
                    "raw_available_count": 30,
                    "rows": [[f"SYM{symbol_index:03d}", 100 - symbol_index] for symbol_index in range(30)],
                }
            )
        for factor_index in range(4):
            weight_snapshots.append(
                {
                    "date": date_text,
                    "window": "1M",
                    "factor": f"factor_{factor_index}",
                    "weight_date": date_text,
                    "rows": [[f"SYM{symbol_index:03d}", 0.03, 2.0] for symbol_index in range(30)],
                }
            )
    line_dates = [f"2026-01-{(index % 28) + 1:02d}" for index in range(180)]
    payload = {
        "schema_version": 1,
        "summary": {"selected_factor": "factor_0"},
        "factor_score_snapshots": score_snapshots,
        "factor_weight_snapshots": weight_snapshots,
        "scenario_available_dates": dates,
        "scenario_available_dates_by_factor": {},
        "factor_backtest_series": [
            {
                "factor": f"factor_{factor_index}",
                "dates": list(line_dates),
                "equity": [1 + index / 1000 for index in range(180)],
                "drawdown": [-index / 10000 for index in range(180)],
            }
            for factor_index in range(12)
        ],
        "benchmark_backtest_series": {
            "symbol": "^IXIC",
            "dates": list(line_dates),
            "equity": [1 + index / 1200 for index in range(180)],
            "drawdown": [-index / 12000 for index in range(180)],
        },
    }

    fitted = _fit_dashboard_payload(payload, max_bytes=80_000)

    assert _json_payload_size(fitted) <= 80_000
    assert fitted["scenario_available_dates"] == ["2026-06-04"]
    assert {snapshot["date"] for snapshot in fitted["factor_score_snapshots"]} == {"2026-06-04"}
    assert {snapshot["date"] for snapshot in fitted["factor_weight_snapshots"]} == {"2026-06-04"}
    assert all(len(snapshot["rows"]) >= 10 for snapshot in fitted["factor_score_snapshots"])
    assert fitted["scenario_available_dates_by_factor"]["factor_0"] == ["2026-06-04"]


def test_payload_fit_recovers_selected_factor_snapshot_from_latest_output_rows():
    payload = {
        "schema_version": 1,
        "summary": {"selected_factor": "mom_9_1", "data_as_of": "2026-06-16"},
        "factor_score_snapshots": [],
        "factor_weight_snapshots": [],
        "latest_output_rows": [
            {"rank": 1, "symbol": "AAA", "score": 3.2, "signal_date": "2026-06-16"},
            {"rank": 2, "symbol": "BBB", "score": 2.1, "signal_date": "2026-06-16"},
        ],
    }

    fitted = _fit_dashboard_payload(payload, max_bytes=50_000)

    assert fitted["scenario_available_dates"] == ["2026-06-16"]
    assert fitted["scenario_available_dates_by_factor"] == {"mom_9_1": ["2026-06-16"]}
    snapshot = fitted["factor_score_snapshots"][0]
    assert snapshot["factor"] == "mom_9_1"
    assert snapshot["score_scope"] == "latest_output_rows_recovery_partial"
    assert snapshot["rows"] == [["AAA", 3.2], ["BBB", 2.1]]
    assert any("latest_output_rows" in note for note in fitted["notes_ko"])


def test_run_results_json_includes_dashboard_payload(tmp_path):
    result = write_reports(
        run_analysis(
            RunConfig(
                start_date="2019-01-01",
                output_dir=tmp_path / "outputs",
                report_dir=tmp_path / "reports",
                offline_sample=True,
                top_n=5,
                max_weight=0.2,
            )
        )
    )

    payload = json.loads(Path(result.output_paths["json"]).read_text(encoding="utf-8"))

    assert "dashboard" in payload
    assert payload["dashboard"]["summary"]["selected_factor"] == result.selected_factor
    assert payload["dashboard"]["factor_leaders"]
    assert payload["dashboard"]["factor_score_snapshots"]
    assert payload["dashboard"]["factor_backtest_series"]
    assert len(json.dumps(payload["dashboard"], ensure_ascii=False).encode("utf-8")) < 5_000_000


def test_public_summary_preserves_zero_weights_for_fail_closed_rows():
    summary = build_public_summary({
        "generated_at_utc": "2026-06-09T00:00:00Z",
        "runs": [{
            "summary": {
                "data_as_of": "2026-06-08",
                "selected_factor": "mom_1m",
                "research_only": True,
                "fail_closed": True,
                "tradability_blockers": ["fixture blocker"],
            },
            "latest_output_rows": [{
                "rank": 1,
                "symbol": "ZERO",
                "score": 1.0,
                "proposed_weight": 0.0,
                "weight": 0.0,
                "selected_factor": "mom_1m",
            }],
        }],
        "latest_run_index": 0,
    })

    metrics = summary["primaryEntities"][0]["metrics"]
    assert metrics["displayWeight"] == 0.0
    assert metrics["finalWeight"] == 0.0


def test_write_dashboard_site_writes_korean_static_files(tmp_path):
    run_payload = {
        "metadata": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "data_as_of": "2026-06-08"},
        "config": {"top_n": 2, "max_weight": 0.1},
        "selected_factor": "mom_1m",
        "dashboard": {
            "schema_version": 1,
            "summary": {
                "run_timestamp_utc": "2026-06-09T00:00:00Z",
                "data_as_of": "2026-06-08",
                "selected_factor": "mom_1m",
                "default_top_n": 2,
                "default_max_weight": 0.1,
            },
            "periods": [{"key": "1M", "label": "최근 1개월", "trading_days": 21}],
            "factor_options": [
                {
                    "factor": "mom_1m",
                    "category": "recent",
                    "description_ko": "최근 가격 상승 강도를 비교합니다.",
                    "selected_by_run": True,
                },
                {
                    "factor": "mom_6m",
                    "category": "traditional",
                    "description_ko": "중기 모멘텀을 비교합니다.",
                    "selected_by_run": False,
                },
            ],
            "factor_leaders": [
                {
                    "date": "2026-06-08",
                    "window": "1M",
                    "window_label": "최근 1개월",
                    "best_factor": "mom_1m",
                    "best_return": 0.12,
                }
            ],
            "factor_period_rankings": [],
            "factor_period_matrix": [
                {
                    "date": "2026-06-08",
                    "window": "1M",
                    "window_label": "최근 1개월",
                    "factors": ["mom_1m", "mom_6m"],
                    "returns": [0.12, 0.05],
                    "factor_count": 2,
                    "exported_factor_count": 2,
                }
            ],
            "holdings": [
                {
                    "date": "2026-06-08",
                    "window": "1M",
                    "window_label": "최근 1개월",
                    "factor": "mom_1m",
                    "rank": 1,
                    "symbol": "AAPL",
                    "score": 1.23,
                    "default_weight": 0.1,
                }
            ],
            "factor_score_snapshots": [
                {
                    "date": "2026-06-08",
                    "factor": "mom_1m",
                    "score_date": "2026-06-07",
                    "available_count": 2,
                    "rows": [["AAPL", 1.23], ["MSFT", 0.8]],
                },
                {
                    "date": "2026-06-08",
                    "factor": "mom_6m",
                    "score_date": "2026-06-07",
                    "available_count": 2,
                    "rows": [["MSFT", 2.0], ["AAPL", 0.5]],
                },
            ],
            "factor_backtest_series": [
                {
                    "factor": "mom_1m",
                    "dates": ["2026-06-06", "2026-06-07", "2026-06-08"],
                    "equity": [1.0, 1.03, 1.12],
                    "drawdown": [0.0, 0.0, 0.0],
                },
                {
                    "factor": "mom_6m",
                    "dates": ["2026-06-06", "2026-06-07", "2026-06-08"],
                    "equity": [1.0, 0.98, 1.05],
                    "drawdown": [0.0, -0.02, 0.0],
                },
            ],
        },
    }
    run_json = tmp_path / "run_results_test.json"
    run_json.write_text(json.dumps(run_payload), encoding="utf-8")

    paths = write_dashboard_site([run_json], tmp_path / "site")

    assert Path(paths["index"]).exists()
    assert Path(paths["data"]).exists()
    assert Path(paths["summary"]).exists()
    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    assert summary["contract"] == "quant-research-summary"
    assert summary["projectId"] == "momentum"
    assert summary["primaryEntities"]
    first_metrics = summary["primaryEntities"][0]["metrics"]
    assert first_metrics["displayWeight"] == 0.1
    assert first_metrics["finalWeight"] == 0.1
    assert any("research-only" in item for item in summary["limitations"])
    html = Path(paths["index"]).read_text(encoding="utf-8")
    css = Path(paths["css"]).read_text(encoding="utf-8")
    js = Path(paths["js"]).read_text(encoding="utf-8")
    assert "모멘텀 팩터 데일리 대시보드" in html
    assert f'assets/styles.css?v={ASSET_VERSION}' in html
    assert f'assets/dashboard.js?v={ASSET_VERSION}' in html
    assert 'href="https://sonchanggi.github.io/quant-dashboard/"' in html
    assert "통합 대시보드로 돌아가기" in html
    assert "hero-link" in css
    assert "다음 수동 실행 입력값을 저장하지 않습니다" in html
    assert "최근 실행 시각" in html
    assert "X축: 날짜" in js
    assert "Y축: 누적 성과" in js
    assert "나스닥 벤치마크" in js
    assert 'id="performance-metrics-table"' in html
    assert "기간별 프록시 성과 지표 비교" in js
    assert "브라우저 프록시" in js
    assert "새 백엔드 재백테스트가 아니라" in js
    assert "실제 일별 구성종목 재매매 결과로 해석하지 마세요" in js
    assert "각 기간 카드에서 같은 지표" in js
    assert "performance-period-grid" in js
    assert "performance-period-card" in js
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "table-layout: fixed" in css
    assert "@media (max-width: 1180px)" in css
    assert "@media (max-width: 720px)" in css
    assert "niceReturnTicks" in js
    assert "dateTickMarks" in js
    assert "최근 1주" in js
    assert "최근 1년" in js
    assert "YTD" in js
    assert "누적 수익률" in js
    assert "샤프지수" in js
    assert "변동성(표준편차)" in js
    assert "소르티노 지수" in js
    assert "칼마 지수" in js
    assert "CVaR(95%)" in js
    assert "최악 5% 일간 손실 평균" in js
    assert "자동 예약 실행과 watchdog 예약은 중지" in html
    assert "publication safety gate" in html
    assert "최신 데이터 업데이트 실행" in html
    assert "검토 후 그 시점의 최신 데이터로 수동 실행" in html
    assert "GitHub Actions에서 최신 데이터 업데이트 실행" in html
    assert "저장소 쓰기 권한" in html
    assert "workflow_dispatch" in html
    assert "Run workflow" in html
    assert 'id="manual-update-button"' in html
    assert 'role="status" aria-live="polite"' in html
    assert "변경사항이 있으면 새 JSON이 커밋" in html
    assert "Actions 상태와 대시보드 기준일" in html
    assert "gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main" in html
    assert "시각화 대시보드" in html
    assert "선택 팩터 시나리오" in html
    assert "브라우저 시나리오 종목당 최대 비중" in html
    assert "표시용 가정" in html
    assert 'id="lookback-months-select"' in html
    assert 'id="topn-input" type="number" min="1" max="50" value="20"' in html
    assert 'id="max-weight-input" type="number" min="1" max="50" step="1" value="50"' in html
    assert 'id="rebalance-select"' in html
    assert 'id="transaction-cost-input"' in html
    assert 'id="slippage-input"' in html
    assert 'id="daily-weight-analysis-panel"' in html
    assert "선택 팩터 일별 투자 비중" in html
    assert "사후 비교 분석" in html
    assert "팩터 수익률 막대 차트" in html
    assert "선택 팩터와 기간 최고 팩터 누적 성과 비교" in html
    assert "상위 N개 모형 비중 시각화" in html
    assert "상위 10개 팩터 동일비중 합산" in html
    assert "기존 결과물 기준 · 해당 날짜 최고 팩터 추천/연구 신호" in html
    assert "기준 팩터" in html
    assert "데이터 품질 · 유동성 · 매매 가능성 게이트" in html
    assert "경제적 의미 · 중복도 · Forward Rank-IC" in html
    assert "후보 종목, 가격 적격, 유동성 적격 종목 수" in html
    assert "JavaScript가 필요합니다" in html
    assert "산출 비중" in html
    assert "최신 출력" in html
    assert "검토된 live-run 입력값" in html
    assert "팩터 점수가 높은 종목에 더 큰 비중" in html
    assert "동일비중" in html
    assert "Top-N" not in html
    assert 'id="factor-select"' in html
    assert 'id="max-weight-input"' in html
    assert 'id="max-weight-input" type="number" min="1" max="50"' in html
    assert "readonly" not in html
    assert "Generated by" not in html
    assert "매일 실행 input" not in html
    assert "renderFactorReturnChart" in js
    assert "renderWeightChart" in js
    assert "renderEnsembleWeightChart" in js
    assert "topFactorEnsembleAllocation" in js
    assert "bestFactorSignalRows" in js
    assert "renderBacktestChart" in js
    assert "DASHBOARD_INPUT_DEFAULTS" in js
    assert "scenarioAdjustedSeriesPoints" in js
    assert "renderDailyWeightsAnalysis" in js
    assert "미표시 후보 합계" in js
    assert "appendBarRow(target, '미표시 후보 합계'" not in js
    assert "computeScenarioAllocation" in js
    assert "renderDiagnostics" in js
    assert "후보 종목" in js
    assert "가격 적격 종목" in js
    assert "유동성 적격 종목" in js
    assert "formatKoreanDateTime" in js
    assert "bindManualUpdateControls" in js
    assert "MANUAL_UPDATE_WORKFLOW_URL" in js
    assert "MANUAL_UPDATE_COMMAND" in js
    assert "typeof navigator === 'undefined'" in js
    assert "저장소 쓰기 권한" in js
    assert "latest-run-at" in js
    assert "appendStatusLine" in js
    assert "최근 실행 시각" in js
    assert "runPayloadGeneratedAt" in js
    assert "사이트 빌드 시각" in js
    assert "renderCurrentOutputTable" in js
    assert "latest_output_rows_fallback" in js
    assert "저장된 latest_output_rows" in js
    assert "renderWithBusy" in js
    assert "팩터 점수 비례 배분" in js
    assert "종목/비중 가능" in js
    assert "recomputeWeights" not in js
    assert "weighted.slice(0, 15)" not in js
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    assert combined["runs"][0]["summary"]["selected_factor"] == "mom_1m"
    assert combined["runs"][0]["factor_score_snapshots"]
    assert combined["runs"][0]["scenario_available_dates"] == ["2026-06-08"]
    assert combined["runs"][0]["scenario_available_dates_by_factor"] == {
        "mom_1m": ["2026-06-08"],
        "mom_6m": ["2026-06-08"],
    }
    assert combined["runs"][0]["factor_backtest_series"]
    assert combined["runs"][0]["history_payload_type"] == "full"
    assert combined["latest_run_index"] == 0
    assert "latest" not in combined
    assert Path(paths["data"]).stat().st_size < 40_000


def test_dashboard_js_scenario_allocation_changes_with_factor_and_cap(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is required for dashboard JavaScript behavior smoke test")

    run_json = tmp_path / "run_results_test.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "summary": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "selected_factor": "factor_a"},
                    "periods": [{"key": "1M", "label": "최근 1개월", "trading_days": 21}],
                    "factor_options": [
                        {"factor": "factor_a", "category": "recent", "description_ko": "단기 모멘텀"},
                        {"factor": "factor_b", "category": "trend", "description_ko": "추세 모멘텀"},
                    ],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "factor_period_matrix": [],
                    "holdings": [],
                    "factor_score_snapshots": [],
                    "factor_backtest_series": [],
                }
            }
        ),
        encoding="utf-8",
    )
    paths = write_dashboard_site([run_json], tmp_path / "site")
    js_path = Path(paths["js"])
    node_script = tmp_path / "scenario-test.mjs"
    node_script.write_text(
        f"""
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync({str(js_path)!r}, 'utf8').replace(/fetch\\('data\\/dashboard\\.json'\\)[\\s\\S]*$/u, '');
const sandbox = {{
  console,
  window: {{ setTimeout: (fn) => fn() }},
  document: {{ querySelector: () => ({{ value: '10', textContent: '', replaceChildren() {{}}, appendChild() {{}}, setAttribute() {{}}, removeAttribute() {{}}, classList: {{ add() {{}}, remove() {{}} }} }}) }},
}};
vm.runInNewContext(source + `
const a = computeScenarioAllocation([['AAA', 3], ['BBB', 2], ['CCC', 1]], 3, 0.10);
const b = computeScenarioAllocation([['ZZZ', 9], ['YYY', 8]], 2, 0.40);
const c = computeScenarioAllocation([['AAA', 5], ['BBB', 4], ['CCC', 3], ['DDD', 2], ['EEE', 1]], 5, 0.50);
const d = computeScenarioAllocation([['HIGH', 0.01], ['ZERO', 0], ['NEG', -10]], 3, 0.90);
const run = {{
  summary: {{
    recommendation_output_key: 'research_signals',
    research_only: true,
    recommendation_output_available: false,
    tradable_output_available: false,
    current_recommendations_available: false,
    tradable_recommendations_available: false,
    same_run_factor_selection_blocked_for_tradable: false,
    same_sample_selection_blocked_for_tradable: false,
  }},
  periods: [{{ key: '1M', label: '최근 1개월' }}],
  factor_period_matrix: [{{
    date: '2026-01-10',
    window: '1M',
    window_label: '최근 1개월',
    factors: ['best_factor', 'second_factor'],
    returns: [0.2, 0.1],
    factor_count: 2,
  }}],
  factor_score_snapshots: [
    {{ date: '2026-01-10', factor: 'best_factor', score_date: '2026-01-10', rows: [['AAA', 9], ['BBB', 8]] }},
    {{ date: '2026-01-10', factor: 'second_factor', score_date: '2026-01-10', rows: [['BBB', 7], ['CCC', 6]] }},
  ],
  factor_weight_snapshots: [
    {{ date: '2026-01-10', window: '1M', factor: 'best_factor', weight_date: '2026-01-10', rows: [['AAA', 0.9, 9], ['BBB', 0.1, 8]] }},
    {{ date: '2026-01-10', window: '1M', factor: 'second_factor', weight_date: '2026-01-10', rows: [['CCC', 0.9, 6], ['BBB', 0.1, 7]] }},
  ],
  latest_output_rows: [
    {{ rank: 1, symbol: 'FALLBACK', score: 5, weight: 0, pre_cap_weight: 0.5, selected_factor: 'saved_factor', signal_date: '2026-01-11' }},
    {{ rank: 2, symbol: 'FALLBACK2', score: 4, weight: 0, pre_cap_weight: 0.25, selected_factor: 'saved_factor', signal_date: '2026-01-11' }},
  ],
}};
const ensemble = topFactorEnsembleAllocation(run, '2026-01-10', '1M', 3, 0.5, 10);
const cappedEnsemble = topFactorEnsembleAllocation(run, '2026-01-10', '1M', 3, 0.3, 10);
const bestRows = bestFactorSignalRows(run, '2026-01-10', '1M', 2, 0.5);
const fallbackRows = bestFactorSignalRows({{ ...run, factor_score_snapshots: [] }}, '2026-01-10', '1M', 2, 0.5);
const savedFactorRows = latestOutputSignalRows(run, 2, 'saved_factor');
const mismatchedFactorRows = latestOutputSignalRows(run, 2, 'other_factor');
const fallbackDateRun = {{
  ...run,
  summary: {{ ...run.summary, selected_factor: 'saved_factor', data_as_of: '2026-01-11' }},
  factor_score_snapshots: [],
  scenario_available_dates: ['2026-01-11'],
  scenario_available_dates_by_factor: {{ saved_factor: ['2026-01-11'] }},
}};
let equity = 1;
const perfPoints = Array.from({{ length: 45 }}, (_, index) => {{
  equity *= index % 7 === 0 ? 0.985 : 1.006;
  const date = new Date(Date.UTC(2026, 0, 2 + index)).toISOString().slice(0, 10);
  return {{ date, equity, normalized: equity }};
}});
const ticks = niceReturnTicks(-0.08, 0.55);
const dateTicks = dateTickMarks(perfPoints.map((point) => point.date));
const perf = performanceMetrics(perfPoints, PERFORMANCE_PERIODS.find((period) => period.key === '1M'));
const risingSeries = {{
  dates: ['2026-01-02', '2026-01-31', '2026-02-27', '2026-03-31'],
  equity: [1, 1.05, 1.12, 1.20],
  drawdown: [0, 0, 0, 0],
}};
const lowCapAllocation = computeScenarioAllocation([['AAA', 9], ['BBB', 8], ['CCC', 7]], 3, 0.10);
const highCapAllocation = computeScenarioAllocation([['AAA', 9], ['BBB', 8], ['CCC', 7]], 3, 0.50);
const monthlyParams = {{ lookbackMonths: 12, topN: 3, maxWeight: 0.10, rebalanceFrequency: 'ME', transactionCostBps: 0, slippageBps: 0, totalCostRate: 0 }};
const lowCapSeries = scenarioAdjustedSeriesPoints(risingSeries, '2026-03-31', monthlyParams, lowCapAllocation);
const highCapSeries = scenarioAdjustedSeriesPoints(risingSeries, '2026-03-31', {{ ...monthlyParams, maxWeight: 0.50 }}, highCapAllocation);
const linkageRun = {{
  periods: [{{ key: '1M', label: '최근 1개월', trading_days: 3 }}],
  factor_period_matrix: [{{
    date: '2026-01-09',
    window: '1M',
    window_label: '최근 1개월',
    factors: ['mom_12_1', 'mom_9_1'],
    returns: [0.12, 0.04],
    factor_count: 2,
  }}],
  factor_score_snapshots: [
    {{ date: '2026-01-09', factor: 'mom_9_1', score_date: '2026-01-08', rows: [['AAA', 100], ['BBB', 2], ['CCC', 1], ['DDD', 1]] }},
    {{ date: '2026-01-09', factor: 'mom_12_1', score_date: '2026-01-08', rows: [['EEE', 5], ['FFF', 5], ['GGG', 5], ['HHH', 5]] }},
  ],
  factor_backtest_series: [
    {{
      factor: 'mom_9_1',
      dates: ['2026-01-01', '2026-01-06', '2026-01-08', '2026-01-09'],
      equity: [1, 1.04, 1.09, 1.14],
      drawdown: [0, 0, 0, 0],
    }},
    {{
      factor: 'mom_12_1',
      dates: ['2026-01-01', '2026-01-06', '2026-01-08', '2026-01-09'],
      equity: [1, 1.02, 1.04, 1.06],
      drawdown: [0, 0, 0, 0],
    }},
  ],
}};
const lowScenarioParams = {{ lookbackMonths: 12, topN: 4, maxWeight: 0.10, rebalanceFrequency: 'ME', transactionCostBps: 0, slippageBps: 0, totalCostRate: 0 }};
const highScenarioParams = {{ ...lowScenarioParams, maxWeight: 0.50 }};
const lowScenarioRows = scenarioPeriodRows(linkageRun, '2026-01-09', '1M', lowScenarioParams);
const highScenarioRows = scenarioPeriodRows(linkageRun, '2026-01-09', '1M', highScenarioParams);
const costlyWeeklyRows = scenarioPeriodRows(linkageRun, '2026-01-09', '1M', {{ ...highScenarioParams, rebalanceFrequency: 'W', transactionCostBps: 100, slippageBps: 0, totalCostRate: 0.01 }});
const freeMonthlyRows = scenarioPeriodRows(linkageRun, '2026-01-09', '1M', highScenarioParams);
const topOneRows = scenarioPeriodRows(linkageRun, '2026-01-09', '1M', {{ ...highScenarioParams, topN: 1 }});
const lookbackDates = Array.from({{ length: 120 }}, (_, index) => {{
  const day = new Date(Date.UTC(2026, 0, 1 + index));
  return day.toISOString().slice(0, 10);
}});
let lookbackMomentumEquity = 1;
let lookbackSteadyEquity = 1;
const lookbackMomentumCurve = lookbackDates.map((_date, index) => {{
  lookbackMomentumEquity *= index < 80 ? 1.001 : 1.012;
  return lookbackMomentumEquity;
}});
const lookbackSteadyCurve = lookbackDates.map(() => {{
  lookbackSteadyEquity *= 1.004;
  return lookbackSteadyEquity;
}});
const lookbackRun = {{
  periods: [{{ key: '1Y', label: '최근 1년', trading_days: 252 }}],
  factor_period_matrix: [{{
    date: lookbackDates.at(-1),
    window: '1Y',
    window_label: '최근 1년',
    factors: ['mom_9_1', 'mom_12_1'],
    returns: [0.7, 0.6],
    factor_count: 2,
  }}],
  factor_score_snapshots: [
    {{ date: lookbackDates.at(-1), factor: 'mom_9_1', score_date: lookbackDates.at(-2), rows: [['AAA', 10], ['BBB', 9], ['CCC', 8], ['DDD', 7]] }},
    {{ date: lookbackDates.at(-1), factor: 'mom_12_1', score_date: lookbackDates.at(-2), rows: [['EEE', 10], ['FFF', 9], ['GGG', 8], ['HHH', 7]] }},
  ],
  factor_backtest_series: [
    {{ factor: 'mom_9_1', dates: lookbackDates, equity: lookbackMomentumCurve, drawdown: lookbackDates.map(() => 0) }},
    {{ factor: 'mom_12_1', dates: lookbackDates, equity: lookbackSteadyCurve, drawdown: lookbackDates.map(() => 0) }},
  ],
}};
const longLookbackRows = scenarioPeriodRows(lookbackRun, lookbackDates.at(-1), '1Y', {{ ...highScenarioParams, lookbackMonths: 12 }});
const shortLookbackRows = scenarioPeriodRows(lookbackRun, lookbackDates.at(-1), '1Y', {{ ...highScenarioParams, lookbackMonths: 1 }});
if (a.weighted[0].symbol !== 'AAA') throw new Error('factor A ranking failed');
if (b.weighted[0].symbol !== 'ZZZ') throw new Error('factor B ranking failed');
if (Math.abs(a.weighted[0].display_weight - 0.10) > 1e-12) throw new Error('max cap was not applied');
if (Math.abs(a.cashTotal - 0.70) > 1e-12) throw new Error('cash remainder from cap missing');
if (Math.abs(b.weighted[0].display_weight - 0.40) > 1e-12) throw new Error('factor B cap failed');
if (Math.abs(b.cashTotal - 0.20) > 1e-12) throw new Error('factor B cash failed');
if (!(c.weighted[0].display_weight > 0.39 && c.weighted[0].display_weight < 0.41)) throw new Error('score-proportional weight failed');
if (!(c.weighted[0].display_weight > c.weighted[1].display_weight && c.weighted[1].display_weight > c.weighted[2].display_weight)) throw new Error('score ordering was not reflected in weights');
if (!(d.weighted[0].display_weight > d.weighted[1].display_weight && d.weighted[1].display_weight > d.weighted[2].display_weight)) throw new Error('mixed sign score ordering was not reflected in weights');
if (!['AAA', 'CCC'].includes(ensemble.weighted[0].symbol)) throw new Error('ensemble did not use factor-internal model weights');
if (Math.abs(ensemble.weighted[0].display_weight - 0.45) > 1e-12) throw new Error('factor-internal model weights were not preserved before final cap');
if (ensemble.factorsUsedCount !== 2) throw new Error('ensemble did not include the best and second factor sleeves');
if (cappedEnsemble.weighted.some((row) => row.display_weight > 0.300000000001)) throw new Error('browser max weight cap was not applied to ensemble');
if (cappedEnsemble.cashTotal <= 0) throw new Error('ensemble cap should leave cash when all candidates hit the cap');
if (bestRows.best.factor !== 'best_factor') throw new Error('best-factor signal did not use period best factor');
if (bestRows.rows[0].symbol !== 'AAA') throw new Error('best-factor signal ranking failed');
if (bestRows.rows[0].weight !== 0) throw new Error('research-only best-factor output must fail closed to zero final weight');
if (bestRows.rows[0].pre_cap_weight <= 0) throw new Error('best-factor diagnostic pre-gate weight missing');
if (fallbackRows.signalSource !== 'latest_output_rows_fallback') throw new Error('latest output fallback not reported');
if (fallbackRows.rows[0].symbol !== 'FALLBACK') throw new Error('latest output fallback row missing');
if (fallbackRows.rows.length !== 2) throw new Error('latest output fallback must respect requested top N');
if (savedFactorRows.length !== 2) throw new Error('matching latest output factor fallback missing');
if (mismatchedFactorRows.length !== 0) throw new Error('mismatched latest output factor must not fallback');
if (!factorAvailableDates(fallbackDateRun, 'saved_factor').has('2026-01-11')) throw new Error('matching latest output factor date fallback missing');
if (factorAvailableDates(fallbackDateRun, 'other_factor').has('2026-01-11')) throw new Error('mismatched latest output factor date must not be available');
if (!ticks.includes(0) || !ticks.includes(0.5)) throw new Error('clean return tick marks missing');
if (dateTicks.length < 4) throw new Error('date tick marks are too sparse');
if (!Number.isFinite(perf.cumulativeReturn)) throw new Error('performance return missing');
if (!Number.isFinite(perf.volatility)) throw new Error('performance volatility missing');
if (!Number.isFinite(perf.maxDrawdown) || perf.maxDrawdown > 0) throw new Error('performance MDD invalid');
if (!(highCapSeries.at(-1).equity > lowCapSeries.at(-1).equity)) throw new Error('max-weight scenario did not affect backtest series');
if (highScenarioRows[0].factor !== 'mom_9_1') throw new Error('scenario rows did not recompute factor ranking from linked input-adjusted returns');
if (!(highScenarioRows.find((row) => row.factor === 'mom_9_1').period_return > lowScenarioRows.find((row) => row.factor === 'mom_9_1').period_return)) throw new Error('max-weight input did not affect factor return rows');
if (!(costlyWeeklyRows.find((row) => row.factor === 'mom_9_1').period_return < freeMonthlyRows.find((row) => row.factor === 'mom_9_1').period_return)) throw new Error('rebalance/cost inputs did not affect factor return rows');
if (topOneRows.find((row) => row.factor === 'mom_9_1').period_return === highScenarioRows.find((row) => row.factor === 'mom_9_1').period_return) throw new Error('top-N input did not affect factor return rows');
if (shortLookbackRows.find((row) => row.factor === 'mom_9_1').period_return === longLookbackRows.find((row) => row.factor === 'mom_9_1').period_return) throw new Error('lookback input did not affect factor return rows');
`, sandbox);
""",
        encoding="utf-8",
    )

    completed = subprocess.run(["node", str(node_script)], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr


def test_dashboard_js_defaults_to_best_factor_and_requested_input_defaults(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is required for dashboard JavaScript behavior smoke test")

    run_json = tmp_path / "run_results_test.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "summary": {
                        "run_timestamp_utc": "2026-06-09T00:00:00Z",
                        "data_as_of": "2026-06-08",
                        "selected_factor": "mom_9_1",
                        "default_top_n": 2,
                        "default_max_weight": 0.1,
                    },
                    "periods": [
                        {"key": "1M", "label": "최근 1개월", "trading_days": 21},
                        {"key": "1Y", "label": "최근 1년", "trading_days": 252},
                    ],
                    "factor_options": [
                        {"factor": "mom_9_1", "category": "traditional", "description_ko": "9개월-1개월"},
                        {"factor": "mom_12_1", "category": "traditional", "description_ko": "12개월-1개월"},
                    ],
                    "factor_leaders": [
                        {"date": "2026-06-08", "window": "1M", "best_factor": "mom_9_1", "best_return": 0.03},
                        {"date": "2026-06-08", "window": "1Y", "best_factor": "mom_12_1", "best_return": 0.22},
                    ],
                    "factor_period_matrix": [
                        {
                            "date": "2026-06-08",
                            "window": "1Y",
                            "window_label": "최근 1년",
                            "factors": ["mom_12_1", "mom_9_1"],
                            "returns": [0.22, 0.11],
                            "factor_count": 2,
                        }
                    ],
                    "factor_period_rankings": [],
                    "holdings": [],
                    "factor_score_snapshots": [
                        {"date": "2026-06-08", "factor": "mom_12_1", "score_date": "2026-06-07", "rows": [["AAA", 9]]}
                    ],
                    "factor_backtest_series": [],
                }
            }
        ),
        encoding="utf-8",
    )
    paths = write_dashboard_site([run_json], tmp_path / "site")
    js_path = Path(paths["js"])
    node_script = tmp_path / "defaults-test.mjs"
    node_script.write_text(
        f"""
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync({str(js_path)!r}, 'utf8').replace(/fetch\\('data\\/dashboard\\.json'\\)[\\s\\S]*$/u, '');
class FakeElement {{
  constructor(selector) {{
    this.selector = selector;
    this.value = '';
    this.textContent = '';
    this.children = [];
    this.disabled = false;
    this.classList = {{ add() {{}}, remove() {{}} }};
  }}
  replaceChildren(...nodes) {{ this.children = nodes; }}
  appendChild(node) {{ this.children.push(node); return node; }}
  append(...nodes) {{ this.children.push(...nodes); }}
  setAttribute() {{}}
  removeAttribute() {{}}
  addEventListener() {{}}
}}
const elements = new Map();
function elementFor(selector) {{
  if (!elements.has(selector)) elements.set(selector, new FakeElement(selector));
  return elements.get(selector);
}}
const document = {{
  querySelector: elementFor,
  querySelectorAll: () => [],
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_ns, tag) => new FakeElement(tag),
  addEventListener() {{}},
}};
const sandbox = {{
  console,
  document,
  window: {{ setTimeout: (fn) => fn(), location: {{ search: '' }}, addEventListener() {{}} }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  URLSearchParams,
}};
vm.runInNewContext(source + `
renderWithBusy('preload preset guard');
if (!document.querySelector('#run-status').textContent.includes('데이터를 불러오는 중')) throw new Error('preload render guard did not explain loading state');
state.data = {{
  latest_run_index: 0,
  runs: [{{
    summary: {{
      run_timestamp_utc: '2026-06-09T00:00:00Z',
      data_as_of: '2026-06-08',
      selected_factor: 'mom_9_1',
      default_top_n: 2,
      default_max_weight: 0.1,
    }},
    periods: [
      {{ key: '1M', label: '최근 1개월', trading_days: 21 }},
      {{ key: '1Y', label: '최근 1년', trading_days: 252 }},
    ],
    factor_options: [
      {{ factor: 'mom_9_1', category: 'traditional', description_ko: '9개월-1개월' }},
      {{ factor: 'mom_12_1', category: 'traditional', description_ko: '12개월-1개월' }},
    ],
    factor_leaders: [
      {{ date: '2026-06-08', window: '1M', best_factor: 'mom_9_1', best_return: 0.03 }},
      {{ date: '2026-06-08', window: '1Y', best_factor: 'mom_12_1', best_return: 0.22 }},
    ],
    factor_period_matrix: [{{
      date: '2026-06-08',
      window: '1Y',
      window_label: '최근 1년',
      factors: ['mom_12_1', 'mom_9_1'],
      returns: [0.22, 0.11],
      factor_count: 2,
    }}],
    factor_period_rankings: [],
    factor_score_snapshots: [
      {{ date: '2026-06-08', factor: 'mom_12_1', score_date: '2026-06-07', rows: [['AAA', 9]] }},
    ],
    holdings: [],
    factor_backtest_series: [],
  }}],
}};
fillControls();
if (document.querySelector('#window-select').value !== '1Y') throw new Error('default window is not recent 12 months');
if (document.querySelector('#factor-select').value !== 'mom_12_1') throw new Error('default factor did not follow current best factor');
if (String(document.querySelector('#topn-input').value) !== '20') throw new Error('default top N is not 20');
if (String(document.querySelector('#max-weight-input').value) !== '50') throw new Error('default max weight is not 50 percent');
if (document.querySelector('#lookback-months-select').value !== '12') throw new Error('default lookback is not 12 months');
if (document.querySelector('#rebalance-select').value !== 'ME') throw new Error('default rebalance is not monthly');
if (document.querySelector('#transaction-cost-input').value !== '5') throw new Error('default transaction cost is not 5 bps');
if (document.querySelector('#slippage-input').value !== '5') throw new Error('default slippage is not 5 bps');
document.querySelector('#window-select').value = '1M';
syncDefaultFactorToCurrentBasis();
if (document.querySelector('#factor-select').value !== 'mom_9_1') throw new Error('basis/window change did not refresh best-factor default');
state.hasUserSelectedFactor = true;
document.querySelector('#factor-select').value = 'mom_9_1';
document.querySelector('#window-select').value = '1Y';
syncDefaultFactorToCurrentBasis();
if (document.querySelector('#factor-select').value !== 'mom_9_1') throw new Error('manual factor selection was overwritten');
`, sandbox);
""",
        encoding="utf-8",
    )

    completed = subprocess.run(["node", str(node_script)], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr


def test_dashboard_js_render_all_survives_zero_snapshot_latest_output_payload(tmp_path):
    run_json = tmp_path / "run.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard_payload": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-17T00:00:00Z",
                    "summary": {
                        "data_as_of": "2026-06-16",
                        "run_timestamp_utc": "2026-06-17T00:19:34Z",
                        "selected_factor": "mom_9_1",
                        "default_top_n": 10,
                        "default_max_weight": 0.1,
                        "research_only": True,
                        "recommendation_output_key": "research_signals",
                        "tradability_blockers": ["실전 매매 게이트 미통과"],
                    },
                    "periods": [{"key": "1M", "label": "최근 1개월"}],
                    "factor_options": [
                        {"factor": "mom_9_1", "category": "traditional", "description_ko": "9개월-1개월 모멘텀"},
                        {"factor": "mom_12_1", "category": "traditional", "description_ko": "12개월-1개월 모멘텀"},
                    ],
                    "factor_leaders": [{"date": "2026-06-16", "window": "1M", "best_factor": "mom_9_1", "best_return": 0.12}],
                    "factor_period_matrix": [
                        {
                            "date": "2026-06-16",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factors": ["mom_9_1", "mom_12_1"],
                            "returns": [0.12, 0.08],
                            "factor_count": 2,
                        }
                    ],
                    "factor_score_snapshots": [],
                    "factor_weight_snapshots": [],
                    "scenario_available_dates": [],
                    "scenario_available_dates_by_factor": {},
                    "factor_backtest_series": [],
                    "latest_output_rows": [
                        {
                            "rank": 1,
                            "symbol": "AAA",
                            "score": 2.5,
                            "weight": 0,
                            "pre_cap_weight": 0.12,
                            "selected_factor": "mom_9_1",
                            "signal_date": "2026-06-16",
                        },
                        {
                            "rank": 2,
                            "symbol": "BBB",
                            "score": 1.8,
                            "weight": 0,
                            "pre_cap_weight": 0.08,
                            "selected_factor": "mom_9_1",
                            "signal_date": "2026-06-16",
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    paths = write_dashboard_site([run_json], tmp_path / "site")
    js_path = Path(paths["js"])
    node_script = tmp_path / "render-all-smoke.mjs"
    node_script.write_text(
        f"""
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync({str(js_path)!r}, 'utf8').replace(/fetch\\('data\\/dashboard\\.json'\\)[\\s\\S]*$/u, '');
class FakeElement {{
  constructor(selector) {{
    this.selector = selector;
    this.value = '';
    this.textContent = '';
    this.children = [];
    this.attributes = {{}};
    this.style = {{ setProperty: (key, value) => {{ this.style[key] = value; }} }};
    this.classList = {{ add() {{}}, remove() {{}}, toggle() {{}} }};
  }}
  replaceChildren(...nodes) {{ this.children = nodes; }}
  appendChild(node) {{ this.children.push(node); return node; }}
  append(...nodes) {{ this.children.push(...nodes); }}
  setAttribute(key, value) {{ this.attributes[key] = value; }}
  removeAttribute(key) {{ delete this.attributes[key]; }}
  addEventListener() {{}}
}}
const elements = new Map();
function elementFor(selector) {{
  if (!elements.has(selector)) elements.set(selector, new FakeElement(selector));
  return elements.get(selector);
}}
const document = {{
  querySelector: elementFor,
  querySelectorAll: () => [],
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_ns, tag) => new FakeElement(tag),
  addEventListener() {{}},
}};
const sandbox = {{
  console,
  document,
  window: {{ setTimeout: (fn) => fn(), location: {{ search: '' }}, addEventListener() {{}} }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  URLSearchParams,
}};
vm.runInNewContext(source + `
state.data = {{
  schema_version: 1,
  latest_run_index: 0,
  runs: [{{
    summary: {{
      data_as_of: '2026-06-16',
      run_timestamp_utc: '2026-06-17T00:19:34Z',
      selected_factor: 'mom_9_1',
      default_top_n: 10,
      default_max_weight: 0.1,
      research_only: true,
      recommendation_output_key: 'research_signals',
      tradability_blockers: ['실전 매매 게이트 미통과'],
    }},
    periods: [{{ key: '1M', label: '최근 1개월' }}],
    factor_options: [
      {{ factor: 'mom_9_1', category: 'traditional', description_ko: '9개월-1개월 모멘텀' }},
      {{ factor: 'mom_12_1', category: 'traditional', description_ko: '12개월-1개월 모멘텀' }},
    ],
    factor_leaders: [{{ date: '2026-06-16', window: '1M', best_factor: 'mom_9_1', best_return: 0.12 }}],
    factor_period_matrix: [{{
      date: '2026-06-16',
      window: '1M',
      window_label: '최근 1개월',
      factors: ['mom_9_1', 'mom_12_1'],
      returns: [0.12, 0.08],
      factor_count: 2,
    }}],
    factor_score_snapshots: [],
    factor_weight_snapshots: [],
    scenario_available_dates: [],
    scenario_available_dates_by_factor: {{}},
    factor_backtest_series: [],
    latest_output_rows: [
      {{ rank: 1, symbol: 'AAA', score: 2.5, weight: 0, pre_cap_weight: 0.12, selected_factor: 'mom_9_1', signal_date: '2026-06-16' }},
      {{ rank: 2, symbol: 'BBB', score: 1.8, weight: 0, pre_cap_weight: 0.08, selected_factor: 'mom_9_1', signal_date: '2026-06-16' }},
    ],
  }}],
}};
state.activeRunIndex = 0;
document.querySelector('#date-select').value = '2026-06-16';
document.querySelector('#window-select').value = '1M';
document.querySelector('#factor-select').value = 'mom_9_1';
document.querySelector('#topn-input').value = '10';
document.querySelector('#max-weight-input').value = '10';
renderAll();
if (!document.querySelector('#holdings-availability').textContent.includes('latest_output_rows')) throw new Error('matching fallback explanation was not rendered');
document.querySelector('#factor-select').value = 'mom_12_1';
renderAll();
if (!document.querySelector('#holdings-availability').textContent.includes('mom_9_1 기준')) throw new Error('mismatched factor explanation was not rendered');
`, sandbox);
""",
        encoding="utf-8",
    )

    completed = subprocess.run(["node", str(node_script)], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr


def test_dashboard_js_render_all_relinks_inputs_to_analysis_panels(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is required for dashboard JavaScript behavior smoke test")

    run_json = tmp_path / "run.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-28T00:00:00Z",
                    "summary": {
                        "data_as_of": "2026-01-09",
                        "run_timestamp_utc": "2026-01-10T00:00:00Z",
                        "selected_factor": "mom_9_1",
                        "default_top_n": 20,
                        "default_max_weight": 0.5,
                        "research_only": True,
                    },
                    "periods": [{"key": "1M", "label": "최근 1개월", "trading_days": 3}],
                    "factor_options": [
                        {"factor": "mom_9_1", "category": "traditional", "description_ko": "9개월-1개월 모멘텀"},
                        {"factor": "mom_12_1", "category": "traditional", "description_ko": "12개월-1개월 모멘텀"},
                    ],
                    "factor_leaders": [
                        {
                            "date": "2026-01-09",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "best_factor": "mom_12_1",
                            "best_return": 0.12,
                        }
                    ],
                    "factor_period_matrix": [
                        {
                            "date": "2026-01-09",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factors": ["mom_12_1", "mom_9_1"],
                            "returns": [0.12, 0.04],
                            "factor_count": 2,
                        }
                    ],
                    "factor_score_snapshots": [
                        {
                            "date": "2026-01-09",
                            "factor": "mom_9_1",
                            "score_date": "2026-01-08",
                            "rows": [["AAA", 100], ["BBB", 2], ["CCC", 1], ["DDD", 1]],
                        },
                        {
                            "date": "2026-01-09",
                            "factor": "mom_12_1",
                            "score_date": "2026-01-08",
                            "rows": [["EEE", 5], ["FFF", 5], ["GGG", 5], ["HHH", 5]],
                        },
                    ],
                    "factor_weight_snapshots": [
                        {
                            "date": "2026-01-09",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factor": "mom_9_1",
                            "weight_date": "2026-01-09",
                            "score_date": "2026-01-08",
                            "rows": [["AAA", 0.7, 100], ["BBB", 0.2, 2], ["CCC", 0.1, 1]],
                        }
                    ],
                    "holdings": [
                        {
                            "date": "2026-01-09",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factor": "mom_9_1",
                            "rank": 1,
                            "symbol": "AAA",
                            "score": 100,
                            "default_weight": 0.7,
                            "score_date": "2026-01-08",
                            "weight_source": "백테스트 일별 보유 비중",
                        },
                        {
                            "date": "2026-01-09",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factor": "mom_9_1",
                            "rank": 2,
                            "symbol": "BBB",
                            "score": 2,
                            "default_weight": 0.2,
                            "score_date": "2026-01-08",
                            "weight_source": "백테스트 일별 보유 비중",
                        },
                        {
                            "date": "2026-01-08",
                            "window": "1M",
                            "window_label": "최근 1개월",
                            "factor": "mom_9_1",
                            "rank": 1,
                            "symbol": "AAA",
                            "score": 90,
                            "default_weight": 0.6,
                            "score_date": "2026-01-07",
                            "weight_source": "백테스트 일별 보유 비중",
                        },
                    ],
                    "factor_backtest_series": [
                        {
                            "factor": "mom_9_1",
                            "dates": ["2026-01-01", "2026-01-06", "2026-01-08", "2026-01-09"],
                            "equity": [1, 1.04, 1.09, 1.14],
                            "drawdown": [0, 0, 0, 0],
                        },
                        {
                            "factor": "mom_12_1",
                            "dates": ["2026-01-01", "2026-01-06", "2026-01-08", "2026-01-09"],
                            "equity": [1, 1.02, 1.04, 1.06],
                            "drawdown": [0, 0, 0, 0],
                        },
                    ],
                    "benchmark_backtest_series": {
                        "symbol": "^IXIC",
                        "dates": ["2026-01-01", "2026-01-06", "2026-01-08", "2026-01-09"],
                        "equity": [1, 1.01, 1.02, 1.03],
                        "drawdown": [0, 0, 0, 0],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    paths = write_dashboard_site([run_json], tmp_path / "site")
    js_path = Path(paths["js"])
    node_script = tmp_path / "input-linkage-render.mjs"
    node_script.write_text(
        f"""
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync({str(js_path)!r}, 'utf8').replace(/fetch\\('data\\/dashboard\\.json'\\)[\\s\\S]*$/u, '');
class FakeElement {{
  constructor(selector) {{
    this.selector = selector;
    this.value = '';
    this.textContent = '';
    this.children = [];
    this.attributes = {{}};
    this.disabled = false;
    this.className = '';
    this.colSpan = 1;
    this.style = {{ setProperty: (key, value) => {{ this.style[key] = value; }} }};
    this.classList = {{ add() {{}}, remove() {{}}, toggle() {{}} }};
  }}
  replaceChildren(...nodes) {{ this.children = nodes; this.textContent = ''; }}
  appendChild(node) {{ this.children.push(node); return node; }}
  append(...nodes) {{ this.children.push(...nodes); }}
  setAttribute(key, value) {{ this.attributes[key] = value; }}
  removeAttribute(key) {{ delete this.attributes[key]; }}
  getAttribute(key) {{ return this.attributes[key] || null; }}
  addEventListener() {{}}
}}
const elements = new Map();
function elementFor(selector) {{
  if (!elements.has(selector)) elements.set(selector, new FakeElement(selector));
  return elements.get(selector);
}}
const document = {{
  querySelector: elementFor,
  querySelectorAll: () => [],
  createElement: (tag) => new FakeElement(tag),
  createElementNS: (_ns, tag) => new FakeElement(tag),
  addEventListener() {{}},
}};
function textOf(node) {{
  if (node === null || node === undefined) return '';
  if (typeof node === 'string') return node;
  return [node.textContent || '', ...(node.children || []).map(textOf)].join(' ');
}}
const sandbox = {{
  console,
  document,
  textOf,
  window: {{ setTimeout: (fn) => fn(), location: {{ search: '' }}, addEventListener() {{}} }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}} }},
  URLSearchParams,
}};
vm.runInNewContext(source + `
state.data = {{
  generated_at_utc: '2026-06-28T00:00:00Z',
  latest_run_index: 0,
  runs: [{{
    generated_at_utc: '2026-06-28T00:00:00Z',
    summary: {{
      data_as_of: '2026-01-09',
      run_timestamp_utc: '2026-01-10T00:00:00Z',
      selected_factor: 'mom_9_1',
      default_top_n: 20,
      default_max_weight: 0.5,
      research_only: true,
    }},
    periods: [{{ key: '1M', label: '최근 1개월', trading_days: 3 }}],
    factor_options: [
      {{ factor: 'mom_9_1', category: 'traditional', description_ko: '9개월-1개월 모멘텀' }},
      {{ factor: 'mom_12_1', category: 'traditional', description_ko: '12개월-1개월 모멘텀' }},
    ],
    factor_leaders: [{{ date: '2026-01-09', window: '1M', window_label: '최근 1개월', best_factor: 'mom_12_1', best_return: 0.12 }}],
    factor_period_matrix: [{{ date: '2026-01-09', window: '1M', window_label: '최근 1개월', factors: ['mom_12_1', 'mom_9_1'], returns: [0.12, 0.04], factor_count: 2 }}],
    factor_score_snapshots: [
      {{ date: '2026-01-09', factor: 'mom_9_1', score_date: '2026-01-08', rows: [['AAA', 100], ['BBB', 2], ['CCC', 1], ['DDD', 1]] }},
      {{ date: '2026-01-09', factor: 'mom_12_1', score_date: '2026-01-08', rows: [['EEE', 5], ['FFF', 5], ['GGG', 5], ['HHH', 5]] }},
    ],
    factor_weight_snapshots: [
      {{ date: '2026-01-09', window: '1M', window_label: '최근 1개월', factor: 'mom_9_1', weight_date: '2026-01-09', score_date: '2026-01-08', rows: [['AAA', 0.7, 100], ['BBB', 0.2, 2], ['CCC', 0.1, 1]] }},
    ],
    holdings: [
      {{ date: '2026-01-09', window: '1M', window_label: '최근 1개월', factor: 'mom_9_1', rank: 1, symbol: 'AAA', score: 100, default_weight: 0.7, score_date: '2026-01-08', weight_source: '백테스트 일별 보유 비중' }},
      {{ date: '2026-01-09', window: '1M', window_label: '최근 1개월', factor: 'mom_9_1', rank: 2, symbol: 'BBB', score: 2, default_weight: 0.2, score_date: '2026-01-08', weight_source: '백테스트 일별 보유 비중' }},
      {{ date: '2026-01-08', window: '1M', window_label: '최근 1개월', factor: 'mom_9_1', rank: 1, symbol: 'AAA', score: 90, default_weight: 0.6, score_date: '2026-01-07', weight_source: '백테스트 일별 보유 비중' }},
    ],
    factor_backtest_series: [
      {{ factor: 'mom_9_1', dates: ['2026-01-01', '2026-01-06', '2026-01-08', '2026-01-09'], equity: [1, 1.04, 1.09, 1.14], drawdown: [0, 0, 0, 0] }},
      {{ factor: 'mom_12_1', dates: ['2026-01-01', '2026-01-06', '2026-01-08', '2026-01-09'], equity: [1, 1.02, 1.04, 1.06], drawdown: [0, 0, 0, 0] }},
    ],
    benchmark_backtest_series: {{ symbol: '^IXIC', dates: ['2026-01-01', '2026-01-06', '2026-01-08', '2026-01-09'], equity: [1, 1.01, 1.02, 1.03], drawdown: [0, 0, 0, 0] }},
  }}],
}};
state.activeRunIndex = 0;
document.querySelector('#date-select').value = '2026-01-09';
document.querySelector('#window-select').value = '1M';
document.querySelector('#factor-select').value = 'mom_9_1';
document.querySelector('#lookback-months-select').value = '12';
document.querySelector('#topn-input').value = '4';
document.querySelector('#max-weight-input').value = '10';
document.querySelector('#rebalance-select').value = 'ME';
document.querySelector('#transaction-cost-input').value = '0';
document.querySelector('#slippage-input').value = '0';
renderAll();
const lowDetail = document.querySelector('#selected-factor-detail').textContent;
if (!document.querySelector('#factor-chart-meta').textContent.includes('브라우저 시나리오/프록시')) throw new Error('factor chart did not disclose scenario/proxy basis');
if (!document.querySelector('#selected-factor-method-summary').textContent.includes('9개월') || !document.querySelector('#selected-factor-method-summary').textContent.includes('1개월')) throw new Error('selected factor formula explanation missing lookback/skip months');
if (!document.querySelector('#selected-factor-method-summary').textContent.includes('브라우저 시나리오/민감도 프록시')) throw new Error('selected factor formula explanation missing proxy disclaimer');
const periodText = textOf(document.querySelector('#period-ranking-table tbody'));
if (!periodText.includes('시나리오') || !periodText.includes('원')) throw new Error('period ranking did not show scenario/raw returns');
const dailyBody = document.querySelector('#daily-weights-table tbody');
if (!dailyBody.children.length || dailyBody.children[0].children.length !== 10) throw new Error('daily weights table did not render the expanded readable schema');
const dailyText = textOf(dailyBody);
if (!dailyText.includes('2026-01-09') || !dailyText.includes('백테스트 일별 보유 비중')) throw new Error('daily weights table did not render dated holdings and source');
if (!document.querySelector('#daily-weight-analysis-note').textContent.includes('리밸런싱') || !document.querySelector('#daily-weight-analysis-note').textContent.includes('성과 프록시')) throw new Error('daily weights note did not separate holdings from performance-only inputs');
document.querySelector('#max-weight-input').value = '50';
renderAll();
const highDetail = document.querySelector('#selected-factor-detail').textContent;
if (lowDetail === highDetail) throw new Error('max-weight input did not change selected factor analysis output');
document.querySelector('#rebalance-select').value = 'W';
document.querySelector('#transaction-cost-input').value = '100';
renderAll();
const weeklyCostDetail = document.querySelector('#selected-factor-detail').textContent;
document.querySelector('#rebalance-select').value = 'ME';
renderAll();
const monthlyCostDetail = document.querySelector('#selected-factor-detail').textContent;
if (weeklyCostDetail === monthlyCostDetail) throw new Error('rebalance/cost input did not change selected factor analysis output');
`, sandbox);
""",
        encoding="utf-8",
    )

    completed = subprocess.run(["node", str(node_script)], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr


def test_dashboard_combined_payload_enforces_hard_size_cap(tmp_path):
    site_dir = tmp_path / "site"
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True)
    bulky_run = {
        "schema_version": 1,
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "summary": {"run_timestamp_utc": "2026-06-07T00:00:00Z", "selected_factor": "old"},
        "periods": [{"key": "1M", "label": "최근 1개월", "trading_days": 21}],
        "factor_options": [{"factor": f"factor_{i}", "description_ko": "x" * 500} for i in range(30)],
        "factor_leaders": [
            {"date": f"2026-01-{(i % 28) + 1:02d}", "window": "1M", "best_factor": "old", "best_return": i / 1000}
            for i in range(200)
        ],
        "factor_period_rankings": [
            {"date": f"2026-01-{(i % 28) + 1:02d}", "window": "1M", "factor": f"factor_{i}", "period_return": i}
            for i in range(600)
        ],
        "factor_period_matrix": [
            {
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "window": "1M",
                "factors": [f"factor_{j}" for j in range(80)],
                "returns": [j / 1000 for j in range(80)],
            }
            for i in range(250)
        ],
        "holdings": [{"symbol": "AAA"}],
    }
    (data_dir / "dashboard.json").write_text(
        json.dumps({"schema_version": 1, "runs": [bulky_run], "latest_run_index": 0}),
        encoding="utf-8",
    )
    latest = {
        "dashboard": {
            "schema_version": 1,
            "generated_at_utc": "2026-06-08T00:00:00Z",
            "summary": {"run_timestamp_utc": "2026-06-08T00:00:00Z", "selected_factor": "latest"},
            "periods": [],
            "factor_options": [{"factor": "latest", "description_ko": "최신"}],
            "factor_leaders": [],
            "factor_period_rankings": [],
            "factor_period_matrix": [],
            "holdings": [],
            "factor_score_snapshots": [
                {
                    "date": "2026-06-08",
                    "factor": "latest",
                    "score_date": "2026-06-07",
                    "rows": [["AAA", 3], ["BBB", 2]],
                }
            ],
        }
    }
    run_json = tmp_path / "run_results_latest.json"
    run_json.write_text(json.dumps(latest), encoding="utf-8")

    paths = write_dashboard_site([run_json], site_dir, history_limit=2)
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))

    assert Path(paths["data"]).stat().st_size <= 5_000_000
    assert combined["payload_limits"]["actual_json_bytes"] <= combined["payload_limits"]["max_json_bytes"]
    assert combined["payload_limits"]["actual_json_bytes"] == Path(paths["data"]).stat().st_size
    assert combined["runs"][-1]["summary"]["selected_factor"] == "latest"
    assert combined["runs"][-1]["factor_score_snapshots"]
    assert combined["runs"][0].get("factor_period_matrix") == []


def test_dashboard_cli_generates_site_from_glob(tmp_path):
    run_json = tmp_path / "run_results_test.json"
    run_json.write_text(
        json.dumps(
            {
                "metadata": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "data_as_of": "2026-06-08"},
                "config": {"top_n": 2, "max_weight": 0.1},
                "selected_factor": "mom_1m",
                "dashboard": {
                    "schema_version": 1,
                    "summary": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "selected_factor": "mom_1m"},
                    "periods": [{"key": "1M", "label": "최근 1개월", "trading_days": 21}],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                },
            }
        ),
        encoding="utf-8",
    )
    site_dir = tmp_path / "site"
    args = cli.build_parser().parse_args(
        ["dashboard", "--run-results", str(tmp_path / "run_results_*.json"), "--site-dir", str(site_dir)]
    )

    paths = cli.dashboard_command(args)

    assert Path(paths["index"]).exists()
    assert (site_dir / "data" / "dashboard.json").exists()


def test_scheduled_dashboard_command_uses_config_and_builder(monkeypatch, tmp_path):
    run_json = tmp_path / "outputs" / "run_results_test.json"
    run_json.parent.mkdir()
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "summary": {"run_timestamp_utc": "2026-06-09T00:00:00Z"},
                    "periods": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                }
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "dashboard-config.json"
    config_path.write_text(
        json.dumps(
            {
                "title": "테스트 대시보드",
                "site_dir": str(tmp_path / "configured-site"),
                "run_args": ["--offline-sample", "--output-dir", str(tmp_path / "outputs")],
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_command(args):
        captured["run_args"] = args
        return {"outputs": {"json": str(run_json)}}

    def fake_write_dashboard_site(paths, site_dir, *, title, history_limit):
        captured["paths"] = paths
        captured["site_dir"] = site_dir
        captured["title"] = title
        captured["history_limit"] = history_limit
        return {"index": str(Path(site_dir) / "index.html")}

    monkeypatch.setattr(cli, "run_command", fake_run_command)
    monkeypatch.setattr(cli, "write_dashboard_site", fake_write_dashboard_site)
    args = cli.build_parser().parse_args(["scheduled-dashboard", "--config", str(config_path)])

    paths = cli.scheduled_dashboard_command(args)

    assert paths["index"].endswith("index.html")
    assert captured["run_args"].command == "run"
    assert captured["site_dir"] == str(tmp_path / "configured-site")
    assert captured["title"] == "테스트 대시보드"
    assert captured["history_limit"] == 60
    assert captured["paths"] == [str(run_json)]



def test_dashboard_site_escapes_title_and_uses_dom_rendering(tmp_path):
    run_json = tmp_path / "run_results_test.json"
    malicious = "<img src=x onerror=alert(1)>"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "summary": {
                        "run_timestamp_utc": "2026-06-09T00:00:00Z",
                        "data_as_of": malicious,
                        "selected_factor": malicious,
                        "default_top_n": 1,
                        "default_max_weight": 0.1,
                    },
                    "periods": [{"key": "latest", "label": "최신", "trading_days": None}],
                    "factor_leaders": [
                        {
                            "date": "2026-06-08",
                            "window": "latest",
                            "window_label": "최신",
                            "best_factor": malicious,
                            "best_return": None,
                        }
                    ],
                    "factor_period_rankings": [],
                    "holdings": [
                        {
                            "date": "2026-06-08",
                            "window": "latest",
                            "window_label": "최신",
                            "factor": malicious,
                            "rank": 1,
                            "symbol": malicious,
                            "score": 1.0,
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json], tmp_path / "site", title=malicious)

    html = Path(paths["index"]).read_text(encoding="utf-8")
    js = Path(paths["js"]).read_text(encoding="utf-8")
    assert malicious not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert ".innerHTML" not in js
    assert "textContent" in js


def test_legacy_run_results_fallback_has_leader_row(tmp_path):
    run_json = tmp_path / "run_results_legacy.json"
    run_json.write_text(
        json.dumps(
            {
                "metadata": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "data_as_of": "2026-06-08"},
                "config": {"top_n": 1, "max_weight": 0.1},
                "selected_factor": "mom_1m",
                "recommendations": [{"rank": 1, "symbol": "AAPL", "score": 1.2, "weight": 0.1}],
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json], tmp_path / "site")
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))

    run = combined["runs"][0]
    assert run["factor_leaders"]
    assert run["factor_leaders"][0]["window"] == "latest"
    assert run["holdings"]




def test_dashboard_sanitizes_legacy_research_signal_rows(tmp_path):
    run_json = tmp_path / "run_results_legacy_research.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-10T00:00:00Z",
                    "summary": {
                        "run_timestamp_utc": "2026-06-10T00:00:00Z",
                        "data_as_of": "2026-06-09",
                        "selected_factor": "mom_9_1",
                        "recommendation_output_label": "Practical recommendations",
                        "decision_support_tier": "practical_recommendations",
                        "selected_reason": (
                            "Same-run validation selection is blocked from tradable recommendation output; "
                            "use a predeclared selected factor or walk-forward selection for practical labels."
                        ),
                    },
                    "periods": [],
                    "factor_options": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                    "factor_score_snapshots": [],
                    "latest_output_rows": [
                        {
                            "rank": 1,
                            "symbol": "VSCO",
                            "score": 1.2,
                            "weight": 0.0,
                            "proposed_weight": 0.1,
                            "pre_cap_weight": 0.2,
                            "target_notional": 10_000,
                            "capacity_status": "pass",
                            "capacity_pass": True,
                            "capacity_warning": "Capacity check passed.",
                            "recommendation_output": "research_signals",
                            "selected_factor_selection_source": "research_validation",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json], tmp_path / "site")
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    run = combined["runs"][0]
    summary = run["summary"]
    row = run["latest_output_rows"][0]

    assert summary["recommendation_output_key"] == "research_signals"
    assert summary["recommendation_output_label"] == "Research signals (not tradable)"
    assert summary["decision_support_tier"] == "research_signals"
    assert summary["research_only"] is True
    assert summary["same_sample_selection_blocked_for_tradable"] is True
    assert "no_same_sample_factor_selection" in summary["tradability_blockers"]
    assert "walk-forward selection for practical labels" not in summary["selected_reason"]
    assert row["proposed_weight"] == 0.0
    assert row["pre_cap_weight"] == 0.2
    assert row["target_notional"] == 0.0
    assert row["capacity_pass"] is False
    assert row["capacity_status"] == "research_only_gate_failed"


def test_dashboard_restores_research_pre_cap_weight_from_raw_scores(tmp_path):
    run_json = tmp_path / "run_results_raw_weight_research.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-10T00:00:00Z",
                    "summary": {
                        "run_timestamp_utc": "2026-06-10T00:00:00Z",
                        "data_as_of": "2026-06-09",
                        "selected_factor": "mom_9_1",
                        "recommendation_output_label": "Research signals (not tradable)",
                        "tradability_blockers": ["point_in_time_universe"],
                    },
                    "periods": [],
                    "factor_options": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                    "factor_score_snapshots": [],
                    "latest_output_rows": [
                        {
                            "rank": 1,
                            "symbol": "AAA",
                            "score": 2.0,
                            "weight": 0.0,
                            "pre_cap_weight": 0.0,
                            "raw_weight_score": 3.0,
                            "target_notional": 10_000,
                            "capacity_status": "pass",
                            "capacity_pass": True,
                            "recommendation_output": "research_signals",
                        },
                        {
                            "rank": 2,
                            "symbol": "BBB",
                            "score": 1.0,
                            "weight": 0.0,
                            "pre_cap_weight": 0.0,
                            "raw_weight_score": 1.0,
                            "target_notional": 5_000,
                            "capacity_status": "pass",
                            "capacity_pass": True,
                            "recommendation_output": "research_signals",
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json], tmp_path / "site")
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    rows = combined["runs"][0]["latest_output_rows"]

    assert rows[0]["weight"] == 0.0
    assert rows[1]["weight"] == 0.0
    assert rows[0]["target_notional"] == 0.0
    assert rows[1]["target_notional"] == 0.0
    assert rows[0]["pre_cap_weight"] == pytest.approx(0.75)
    assert rows[1]["pre_cap_weight"] == pytest.approx(0.25)


def test_dashboard_preserves_predeclared_factor_policy_when_other_gate_fails(tmp_path):
    run_json = tmp_path / "run_results_predeclared_research.json"
    run_json.write_text(
        json.dumps(
            {
                "metadata": {
                    "run_timestamp_utc": "2026-06-10T00:00:00Z",
                    "data_as_of": "2026-06-09",
                    "recommendation_output_key": "research_signals",
                    "recommendation_output_label": "Research signals (not tradable)",
                    "recommendation_output_available": False,
                    "tradable_output_available": False,
                    "current_recommendations_available": False,
                    "tradable_recommendations_available": False,
                    "research_only": True,
                    "decision_support_tier": "research_signals",
                    "selected_factor_selection_source": "predeclared",
                    "factor_selection_mode": "predeclared",
                    "selection_policy_frozen_for_live": True,
                    "same_run_factor_selection_blocked_for_tradable": False,
                    "same_sample_selection_blocked_for_tradable": False,
                    "factor_selection_warning": None,
                    "tradability_requirements": {
                        "fresh_live_data": True,
                        "factor_selection_policy_available": True,
                        "no_same_sample_factor_selection": True,
                        "complete_requested_price_coverage": False,
                    },
                    "tradability_blockers": ["complete_requested_price_coverage"],
                    "execution_limitations": ["complete_requested_price_coverage"],
                    "fail_closed_reasons": ["complete_requested_price_coverage"],
                },
                "config": {
                    "top_n": 1,
                    "max_weight": 0.1,
                    "factor_selection_mode": "predeclared",
                    "selected_factor": "mom_9_1",
                    "chart_benchmark": "^IXIC",
                },
                "selected_factor": "mom_9_1",
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-10T00:00:00Z",
                    "summary": {
                        "run_timestamp_utc": "2026-06-10T00:00:00Z",
                        "data_as_of": "2026-06-09",
                        "selected_factor": "mom_9_1",
                    },
                    "periods": [],
                    "factor_options": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                    "factor_score_snapshots": [],
                    "latest_output_rows": [
                        {
                            "rank": 1,
                            "symbol": "AAPL",
                            "score": 1.2,
                            "weight": 0.1,
                            "proposed_weight": 0.1,
                            "capacity_status": "pass",
                            "capacity_pass": True,
                            "recommendation_output": "research_signals",
                            "selected_factor_selection_source": "predeclared",
                        }
                    ],
                    "factor_backtest_series": [],
                    "benchmark_backtest_series": [],
                },
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json], tmp_path / "site")
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    run = combined["runs"][0]
    summary = run["summary"]
    gates = {gate["key"]: gate for gate in run["tradability_gate"]}
    row = run["latest_output_rows"][0]

    assert summary["research_only"] is True
    assert summary["selected_factor_selection_source"] == "predeclared"
    assert summary["same_run_factor_selection_blocked_for_tradable"] is False
    assert summary["same_sample_selection_blocked_for_tradable"] is False
    assert summary["factor_selection_warning"] is None
    assert summary["tradability_requirements"]["factor_selection_policy_available"] is True
    assert summary["tradability_requirements"]["no_same_sample_factor_selection"] is True
    assert "factor_selection_policy_available" not in summary["tradability_blockers"]
    assert "no_same_sample_factor_selection" not in summary["fail_closed_reasons"]
    assert gates["factor_selection_policy_available"]["passed"] is True
    assert gates["no_same_sample_factor_selection"]["passed"] is True
    assert row["weight"] == 0.0
    assert row["capacity_status"] == "research_only_gate_failed"


def test_scheduled_dashboard_json_output_is_parseable(monkeypatch, tmp_path, capsys):
    run_json = tmp_path / "outputs" / "run_results_test.json"
    run_json.parent.mkdir()
    run_json.write_text(json.dumps({"dashboard": {"schema_version": 1}}), encoding="utf-8")
    config_path = tmp_path / "dashboard-config.json"
    config_path.write_text(
        json.dumps({"run_args": ["--offline-sample"], "site_dir": str(tmp_path / "site")}),
        encoding="utf-8",
    )

    def noisy_run_command(args):
        print("this run summary should be suppressed")
        return {"outputs": {"json": str(run_json)}}

    monkeypatch.setattr(cli, "run_command", noisy_run_command)
    monkeypatch.setattr(
        cli,
        "write_dashboard_site",
        lambda paths, site_dir, *, title, history_limit: {"index": str(Path(site_dir) / "index.html")},
    )
    args = cli.build_parser().parse_args(["scheduled-dashboard", "--config", str(config_path), "--json"])

    cli.scheduled_dashboard_command(args)

    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed["index"].endswith("index.html")
    assert "suppressed" not in stdout


def test_dashboard_history_preserves_dedupes_sorts_and_caps(tmp_path):
    site_dir = tmp_path / "site"
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True)
    existing_run_old = {
        "schema_version": 1,
        "generated_at_utc": "2026-06-07T00:00:00Z",
        "summary": {"run_timestamp_utc": "2026-06-07T00:00:00Z", "selected_factor": "old"},
        "periods": [],
        "factor_leaders": [],
        "factor_period_rankings": [],
        "holdings": [],
    }
    existing_run_dup = {
        "schema_version": 1,
        "generated_at_utc": "2026-06-08T00:00:00Z",
        "summary": {"run_timestamp_utc": "2026-06-08T00:00:00Z", "selected_factor": "old-duplicate"},
        "periods": [],
        "factor_leaders": [],
        "factor_period_rankings": [],
        "holdings": [],
    }
    (data_dir / "dashboard.json").write_text(
        json.dumps({"schema_version": 1, "runs": [existing_run_old, existing_run_dup], "latest_run_index": 1}),
        encoding="utf-8",
    )
    run_json = tmp_path / "run_results_new.json"
    run_json.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-08T01:00:00Z",
                    "summary": {"run_timestamp_utc": "2026-06-08T00:00:00Z", "selected_factor": "newer-duplicate"},
                    "periods": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                }
            }
        ),
        encoding="utf-8",
    )
    run_json_2 = tmp_path / "run_results_new2.json"
    run_json_2.write_text(
        json.dumps(
            {
                "dashboard": {
                    "schema_version": 1,
                    "generated_at_utc": "2026-06-09T00:00:00Z",
                    "summary": {"run_timestamp_utc": "2026-06-09T00:00:00Z", "selected_factor": "latest"},
                    "periods": [],
                    "factor_leaders": [],
                    "factor_period_rankings": [],
                    "holdings": [],
                }
            }
        ),
        encoding="utf-8",
    )

    paths = write_dashboard_site([run_json, run_json_2], site_dir, history_limit=2)

    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    factors = [run["summary"]["selected_factor"] for run in combined["runs"]]
    assert factors == ["newer-duplicate", "latest"]
    assert combined["runs"][0]["history_payload_type"] == "summary"
    assert combined["runs"][0]["holdings"] == []
    assert combined["runs"][1]["history_payload_type"] == "full"
    assert combined["latest_run_index"] == 1

def test_daily_dashboard_workflow_has_scheduled_refresh_and_watchdog_fallbacks():
    workflow = Path(".github/workflows/daily-dashboard.yml").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    config = json.loads(Path(".github/momentum-dashboard-config.json").read_text(encoding="utf-8"))

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "0 0 * * 2-6"' in workflow
    assert "09:00 KST Tue-Sat" in workflow
    assert "concurrency:" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "Refresh checkout to latest branch head" in workflow
    assert "dashboard_freshness" in workflow
    assert "continue-on-error: true" in workflow
    assert "Remote branch already has a dashboard execution after 08:00 KST" in workflow
    assert "dashboard_monotonic" in workflow
    assert "--min-latest-output-rows" not in workflow
    assert "Push attempt ${attempt} failed" in workflow

    watchdog = Path(".github/workflows/daily-dashboard-watchdog.yml").read_text(encoding="utf-8")
    assert "Daily Momentum Dashboard Watchdog" in watchdog
    assert "workflow_dispatch:" in watchdog
    assert "schedule:" in watchdog
    for cron in ['cron: "0 1 * * 2-6"', 'cron: "0 3 * * 2-6"', 'cron: "0 6 * * 2-6"', 'cron: "0 9 * * 2-6"']:
        assert cron in watchdog
    assert "freshness-gated fallback checks" in watchdog
    assert "actions: write" in watchdog
    assert "dashboard_freshness" in watchdog
    assert "DASHBOARD_FRESHNESS_EVENT_NAME: schedule" in watchdog
    assert '--event-name "${DASHBOARD_FRESHNESS_EVENT_NAME}"' in watchdog
    assert "GITHUB_EVENT_NAME: schedule" not in watchdog
    assert "gh workflow run daily-dashboard.yml" in watchdog
    assert "steps.freshness.outputs.skip != 'true'" in watchdog
    assert "daily-dashboard-watchdog.yml" in readme
    assert "09:00 KST Tue-Sat" in readme
    assert "10:00/12:00/15:00/18:00 KST Tue-Sat" in readme
    assert "freshness-gated fallback checks" in readme
    assert "publication safety gate" in readme
    assert "workflow_dispatch" in readme
    assert "최신 데이터 업데이트 실행" in readme
    assert "저장소 쓰기 권한" in readme
    assert "그 시점의 가장 최근" in readme
    assert "no `docs/` diff" in readme
    assert "gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main" in readme
    assert "GitHub token" in readme
    assert config["site_dir"] == "docs"
    assert "--live" in config["run_args"]
    assert "--selected-factor" in config["run_args"]
    assert "mom_9_1" in config["run_args"]
    assert "--chart-benchmark" in config["run_args"]
    assert "^IXIC" in config["run_args"]
    assert "--frozen-policy-path" in config["run_args"]
    retry_index = config["run_args"].index("--retry-count")
    assert config["run_args"][retry_index + 1] == "2"
    policy_index = config["run_args"].index("--frozen-policy-path")
    assert config["run_args"][policy_index + 1] == "configs/factor-selection-policy.mom_9_1.v1.json"
    assert config["history_limit"] == 30
    mode_index = config["run_args"].index("--factor-selection-mode")
    assert config["run_args"][mode_index + 1] == "predeclared"


def test_dashboard_monotonic_rejects_candidate_with_collapsed_publication_rows(tmp_path):
    from momentum_factor_lab.dashboard_monotonic import decide_monotonic_dashboard, load_dashboard_snapshot

    def payload(symbols: list[str], snapshot_rows: int, *, data_as_of: str = "2026-06-19") -> dict[str, object]:
        return {
            "generated_at_utc": f"{data_as_of}T10:00:00+00:00",
            "latest_run_index": 0,
            "runs": [{
                "summary": {
                    "data_as_of": data_as_of,
                    "run_timestamp_utc": f"{data_as_of}T09:00:00+00:00",
                    "selected_factor": "mom_9_1",
                },
                "latest_output_rows": [{"symbol": symbol, "rank": index + 1} for index, symbol in enumerate(symbols)],
                "factor_score_snapshots": [{
                    "date": data_as_of,
                    "factor": "mom_9_1",
                    "rows": [[f"S{index:02d}", 1.0 - index / 100] for index in range(snapshot_rows)],
                }],
            }],
        }

    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(payload([f"B{index:02d}" for index in range(20)], 35)), encoding="utf-8")
    candidate_path.write_text(json.dumps(payload(["RSHGY", "GALDY", "TCNNF"], 3)), encoding="utf-8")

    decision = decide_monotonic_dashboard(
        load_dashboard_snapshot(baseline_path),
        load_dashboard_snapshot(candidate_path),
    )

    assert not decision.passed
    assert "collapsed" in decision.reason or "retained too little" in decision.reason


def test_dashboard_css_template_keeps_mobile_overflow_guards():
    docs_css = (Path(__file__).resolve().parents[1] / "docs" / "assets" / "styles.css").read_text(encoding="utf-8")
    required_guards = [
        "html, body { max-width: 100%; overflow-x: hidden; }",
        ".panel, .controls > *, .cards > *, .two-col > *, .viz-grid > *, .diagnostic-grid > *, .manual-update > * { min-width: 0; }",
        ".viz-card {\n  min-width: 0; max-width: 100%;",
        ".viz-card-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: start; margin-bottom: .9rem; min-width: 0; }",
        ".chart-meta { color: var(--muted); font-size: .82rem; font-weight: 800; text-align: right; line-height: 1.4; overflow-wrap: anywhere; min-width: 0; }",
        ".bar-chart { display: grid; gap: .62rem; min-width: 0; }",
        ".bar-row { display: grid; grid-template-columns: minmax(0, .9fr) minmax(140px, 2fr) 88px; gap: .75rem; align-items: center; min-width: 0; }",
        ".line-chart { min-height: 260px; max-width: 100%; min-width: 0;",
    ]
    for guard in required_guards:
        assert guard in CSS_CONTENT
        assert guard in docs_css


def test_dashboard_embedded_assets_stay_synced_with_static_site():
    repo_root = Path(__file__).resolve().parents[1]
    docs_html = (repo_root / "docs" / "index.html").read_text(encoding="utf-8")
    docs_css = (repo_root / "docs" / "assets" / "styles.css").read_text(encoding="utf-8")
    docs_js = (repo_root / "docs" / "assets" / "dashboard.js").read_text(encoding="utf-8")

    rendered_html = HTML_TEMPLATE.format(title="모멘텀 팩터 데일리 대시보드", asset_version=ASSET_VERSION)

    assert rendered_html == docs_html
    assert CSS_CONTENT == docs_css
    assert JS_CONTENT == docs_js
    assert 'id="selected-factor-method-title"' in rendered_html
    assert "scenarioPeriodRows" in JS_CONTENT
    assert "selectedDailyWeightRows" in JS_CONTENT
