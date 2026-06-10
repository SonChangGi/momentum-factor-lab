import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from momentum_factor_lab import cli
from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.dashboard import _holding_rows, build_dashboard_payload, write_dashboard_site
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
    assert payload["factor_backtest_series"]
    assert {"factor", "dates", "equity", "drawdown"}.issubset(payload["factor_backtest_series"][0])
    assert payload["benchmark_backtest_series"]["symbol"] == "^IXIC"
    assert payload["benchmark_backtest_series"]["label_ko"] == "나스닥 종합지수"
    assert payload["benchmark_backtest_series"]["dates"]
    assert payload["holdings"]
    assert {"symbol", "score", "default_weight", "window", "weight_source"}.issubset(payload["holdings"][0])
    assert payload["holdings"][0]["weight_source"] == "백테스트 일별 보유 비중"
    assert payload["data_quality_summary"]["candidate_universe_size"] >= 2000
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
    html = Path(paths["index"]).read_text(encoding="utf-8")
    js = Path(paths["js"]).read_text(encoding="utf-8")
    assert "모멘텀 팩터 데일리 대시보드" in html
    assert "다음 자동 실행 설정을 저장하지 않습니다" in html
    assert "최근 실행 시각" in html
    assert "X축: 날짜" in js
    assert "Y축: 누적 성과" in js
    assert "나스닥 벤치마크" in js
    assert 'id="performance-metrics-table"' in html
    assert "기간별 성과 지표 비교" in js
    assert "각 기간 카드에서 같은 지표" in js
    assert "performance-period-grid" in js
    assert "performance-period-card" in js
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
    assert "08:17을 기본 실행 시각" in html
    assert "이미 실행된 경우" in html
    assert "최신 데이터 업데이트 실행" in html
    assert "자동화 실패 시 그 시점의 최신 데이터" in html
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
    assert "사후 비교 분석" in html
    assert "팩터 수익률 막대 차트" in html
    assert "선택 팩터와 기간 최고 팩터 누적 성과 비교" in html
    assert "상위 N개 모형 비중 시각화" in html
    assert "데이터 품질 · 유동성 · 매매 가능성 게이트" in html
    assert "경제적 의미 · 중복도 · Forward Rank-IC" in html
    assert "후보 종목, 가격 적격, 유동성 적격 종목 수" in html
    assert "JavaScript가 필요합니다" in html
    assert "산출 비중" in html
    assert "최신 출력" in html
    assert "매일 실행 입력값" in html
    assert "팩터 점수가 높은 종목에 더 큰 비중" in html
    assert "동일가중" not in html
    assert "Top-N" not in html
    assert 'id="factor-select"' in html
    assert 'id="max-weight-input"' in html
    assert 'id="max-weight-input" type="number" min="1" max="50"' in html
    assert "readonly" not in html
    assert "Generated by" not in html
    assert "매일 실행 input" not in html
    assert "renderFactorReturnChart" in js
    assert "renderWeightChart" in js
    assert "renderBacktestChart" in js
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
let equity = 1;
const perfPoints = Array.from({{ length: 45 }}, (_, index) => {{
  equity *= index % 7 === 0 ? 0.985 : 1.006;
  const date = new Date(Date.UTC(2026, 0, 2 + index)).toISOString().slice(0, 10);
  return {{ date, equity, normalized: equity }};
}});
const ticks = niceReturnTicks(-0.08, 0.55);
const dateTicks = dateTickMarks(perfPoints.map((point) => point.date));
const perf = performanceMetrics(perfPoints, PERFORMANCE_PERIODS.find((period) => period.key === '1M'));
if (a.weighted[0].symbol !== 'AAA') throw new Error('factor A ranking failed');
if (b.weighted[0].symbol !== 'ZZZ') throw new Error('factor B ranking failed');
if (Math.abs(a.weighted[0].display_weight - 0.10) > 1e-12) throw new Error('max cap was not applied');
if (Math.abs(a.cashTotal - 0.70) > 1e-12) throw new Error('cash remainder from cap missing');
if (Math.abs(b.weighted[0].display_weight - 0.40) > 1e-12) throw new Error('factor B cap failed');
if (Math.abs(b.cashTotal - 0.20) > 1e-12) throw new Error('factor B cash failed');
if (!(c.weighted[0].display_weight > 0.39 && c.weighted[0].display_weight < 0.41)) throw new Error('score-proportional weight failed');
if (!(c.weighted[0].display_weight > c.weighted[1].display_weight && c.weighted[1].display_weight > c.weighted[2].display_weight)) throw new Error('score ordering was not reflected in weights');
if (!(d.weighted[0].display_weight > d.weighted[1].display_weight && d.weighted[1].display_weight > d.weighted[2].display_weight)) throw new Error('mixed sign score ordering was not reflected in weights');
if (!ticks.includes(0) || !ticks.includes(0.5)) throw new Error('clean return tick marks missing');
if (dateTicks.length < 4) throw new Error('date tick marks are too sparse');
if (!Number.isFinite(perf.cumulativeReturn)) throw new Error('performance return missing');
if (!Number.isFinite(perf.volatility)) throw new Error('performance volatility missing');
if (!Number.isFinite(perf.maxDrawdown) || perf.maxDrawdown > 0) throw new Error('performance MDD invalid');
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
    assert row["pre_cap_weight"] == 0.0
    assert row["target_notional"] == 0.0
    assert row["capacity_pass"] is False
    assert row["capacity_status"] == "research_only_gate_failed"



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

def test_daily_dashboard_workflow_documents_kst_schedule():
    workflow = Path(".github/workflows/daily-dashboard.yml").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    config = json.loads(Path(".github/momentum-dashboard-config.json").read_text(encoding="utf-8"))

    assert "cron: '17 23 * * *'" in workflow
    assert "cron: '47 23 * * *'" in workflow
    assert "cron: '17 0 * * *'" in workflow
    assert "08:17 KST" in workflow
    assert "08:00 KST" in workflow
    assert "concurrency:" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "Refresh checkout to latest branch head" in workflow
    assert "dashboard_freshness" in workflow
    assert "continue-on-error: true" in workflow
    assert "Remote branch already has a dashboard execution after 08:00 KST" in workflow
    assert "workflow_dispatch:" in workflow
    assert "23:17 UTC" in readme
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
    mode_index = config["run_args"].index("--factor-selection-mode")
    assert config["run_args"][mode_index + 1] == "predeclared"
