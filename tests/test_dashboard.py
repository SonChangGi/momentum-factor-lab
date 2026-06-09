import json
from pathlib import Path

from momentum_factor_lab import cli
from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.dashboard import build_dashboard_payload, write_dashboard_site
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
    assert {"symbol", "score", "default_weight", "window"}.issubset(payload["holdings"][0])
    assert payload["notes_ko"][0].startswith("웹사이트 입력값")


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
    assert "모멘텀 팩터 데일리 대시보드" in Path(paths["index"]).read_text(encoding="utf-8")
    assert "다음 자동 실행 설정을 저장하지 않습니다" in Path(paths["index"]).read_text(encoding="utf-8")
    combined = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    assert combined["runs"][0]["summary"]["selected_factor"] == "mom_1m"
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

    def fake_write_dashboard_site(paths, site_dir, *, title):
        captured["paths"] = paths
        captured["site_dir"] = site_dir
        captured["title"] = title
        return {"index": str(Path(site_dir) / "index.html")}

    monkeypatch.setattr(cli, "run_command", fake_run_command)
    monkeypatch.setattr(cli, "write_dashboard_site", fake_write_dashboard_site)
    args = cli.build_parser().parse_args(["scheduled-dashboard", "--config", str(config_path)])

    paths = cli.scheduled_dashboard_command(args)

    assert paths["index"].endswith("index.html")
    assert captured["run_args"].command == "run"
    assert captured["site_dir"] == str(tmp_path / "configured-site")
    assert captured["title"] == "테스트 대시보드"
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
    monkeypatch.setattr(cli, "write_dashboard_site", lambda paths, site_dir, *, title: {"index": str(Path(site_dir) / "index.html")})
    args = cli.build_parser().parse_args(["scheduled-dashboard", "--config", str(config_path), "--json"])

    cli.scheduled_dashboard_command(args)

    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed["index"].endswith("index.html")
    assert "suppressed" not in stdout

def test_daily_dashboard_workflow_documents_kst_schedule():
    workflow = Path(".github/workflows/daily-dashboard.yml").read_text(encoding="utf-8")
    config = json.loads(Path(".github/momentum-dashboard-config.json").read_text(encoding="utf-8"))

    assert "cron: '0 23 * * *'" in workflow
    assert "08:00 KST" in workflow or "08:00 Korea" in workflow
    assert config["site_dir"] == "docs"
    assert "--live" in config["run_args"]
