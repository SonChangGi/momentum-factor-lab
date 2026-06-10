import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

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
    assert payload["factor_leaders"]
    assert {"date", "window", "best_factor", "best_return"}.issubset(payload["factor_leaders"][0])
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
    assert len(json.dumps(payload["dashboard"], ensure_ascii=False)) < 2_500_000


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
    assert "08:17을 기본 실행 시각" in html
    assert "이미 실행된 경우" in html
    assert "시각화 대시보드" in html
    assert "팩터 수익률 막대 차트" in html
    assert "상위 N개 모형 비중 시각화" in html
    assert "데이터 품질 · 유동성 · 매매 가능성 게이트" in html
    assert "경제적 의미 · 중복도 · Forward Rank-IC" in html
    assert "후보 종목, 가격 적격, 유동성 적격 종목 수" in html
    assert "JavaScript가 필요합니다" in html
    assert "산출 비중" in html
    assert "최신 출력" in html
    assert "매일 실행 입력값" in html
    assert "동일가중" not in html
    assert "Top-N" not in html
    assert "Generated by" not in html
    assert "매일 실행 input" not in html
    assert "renderFactorReturnChart" in js
    assert "renderWeightChart" in js
    assert "renderDiagnostics" in js
    assert "후보 종목" in js
    assert "가격 적격 종목" in js
    assert "유동성 적격 종목" in js
    assert "formatKoreanDateTime" in js
    assert "latest-run-at" in js
    assert "appendStatusLine" in js
    assert "최근 실행 시각" in js
    assert "runPayloadGeneratedAt" in js
    assert "사이트 빌드 시각" in js
    assert "renderCurrentOutputTable" in js
    assert "renderWithBusy" in js
    assert "recomputeWeights" not in js
    assert "weighted.slice(0, 15)" not in js
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    assert combined["runs"][0]["summary"]["selected_factor"] == "mom_1m"
    assert combined["runs"][0]["history_payload_type"] == "full"
    assert combined["latest_run_index"] == 0
    assert "latest" not in combined
    assert Path(paths["data"]).stat().st_size < 20_000


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
    assert config["site_dir"] == "docs"
    assert "--live" in config["run_args"]
