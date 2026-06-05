import json
from pathlib import Path

import openpyxl
import pandas as pd

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.data import MarketData
from momentum_factor_lab.report import write_reports
from momentum_factor_lab.universe import universe_frame_for_symbols
from momentum_factor_lab.workflow import run_analysis, write_run_results_json


def test_offline_run_generates_required_outputs(tmp_path):
    config = RunConfig(
        start_date="2019-01-01",
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=True,
    )
    result = write_reports(run_analysis(config))
    pdf = Path(result.output_paths["pdf"])
    xlsx = Path(result.output_paths["xlsx"])
    json_path = Path(result.output_paths["json"])
    assert pdf.exists() and pdf.stat().st_size > 5_000
    assert xlsx.exists() and xlsx.stat().st_size > 5_000
    assert json_path.exists()
    workbook = openpyxl.load_workbook(xlsx, read_only=True)
    required = {
        "config_assumptions",
        "universe",
        "factor_scores",
        "factor_score_history_top20",
        "data_sources",
        "price_sources",
        "factor_definitions",
        "factor_validation",
        "backtest_metrics",
        "score_components",
        "benchmark_relative",
        "selected_factor_scores",
        "selected_factor",
        "recommendations",
        "exclusions",
        "robustness",
        "sensitivity",
    }
    assert required.issubset(set(workbook.sheetnames))
    assert result.metadata["recommendation_status"] == "sample_offline_not_current"
    assert not result.metadata["current_recommendations_available"]
    assert "validation" in set(result.robustness["slice"])
    assert result.score_components.index[0] == result.selected_factor
    assert not result.benchmark_relative.empty
    assert len(result.recommendations) == result.config.top_n
    assert result.metadata["candidate_universe_size"] >= 2000
    assert result.metadata["factor_count"] >= 18
    assert result.metadata["factor_validation_status"] == "pass"
    assert {"variant_type", "variant", "parameter_set"}.issubset(result.sensitivity.columns)
    factor_sheet = workbook["factor_scores"]
    history_sheet = workbook["factor_score_history_top20"]
    assert factor_sheet.max_row > len(result.market_data.prices.columns)
    assert history_sheet.max_row < 1_048_576


def test_live_failure_or_offline_status_never_claims_current(tmp_path, monkeypatch):
    config = RunConfig(output_dir=tmp_path / "outputs", report_dir=tmp_path / "reports", offline_sample=True)
    result = run_analysis(config)
    assert result.metadata["recommendation_status"] != "current_live"
    assert not result.metadata["current_recommendations_available"]


def test_stale_live_data_zeroes_recommendation_weights(tmp_path, monkeypatch):
    dates = pd.bdate_range("2020-01-01", periods=320)
    symbols = ["SPY", "AAA", "BBB", "CCC", "DDD"]
    prices = pd.DataFrame(
        {symbol: [100 + i + day * (0.02 + i * 0.001) for day in range(len(dates))] for i, symbol in enumerate(symbols)},
        index=dates,
    )
    volumes = pd.DataFrame(1_000_000, index=dates, columns=symbols)

    stale_market_data = MarketData(
        prices=prices,
        volumes=volumes,
        provider="test-live-provider",
        fetched_at=pd.Timestamp("2020-03-01", tz="UTC").to_pydatetime(),
        as_of=prices.index.max(),
        exclusions=pd.DataFrame(columns=["symbol", "reason", "observed"]),
        offline_sample=False,
        candidate_universe=universe_frame_for_symbols(symbols),
        eligible_universe=universe_frame_for_symbols(symbols),
        price_sources=pd.DataFrame(
            {"symbol": symbols, "price_source": "test-adjusted-daily", "adjustment_note": "test"}
        ),
        data_sources=pd.DataFrame(
            [
                {
                    "source": "live-run-summary",
                    "status": "full_requested_universe",
                    "records": len(symbols),
                    "candidate_symbols": len(symbols),
                    "requested_price_symbols": len(symbols),
                    "eligible_price_symbols": len(symbols),
                    "excluded_symbols": 0,
                    "subset_run": False,
                }
            ]
        ),
    )

    monkeypatch.setattr("momentum_factor_lab.workflow.load_market_data", lambda config: stale_market_data)

    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        top_n=3,
        max_weight=0.5,
        stale_after_days=1,
    )
    result = run_analysis(config)

    assert result.metadata["recommendation_status"].startswith("stale_live_data_")
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()
    assert result.recommendations["recommendation_status"].eq(result.metadata["recommendation_status"]).all()
    assert result.recommendations["signal_date"].eq(str(prices.index.max().date())).all()


def test_json_export_preserves_recommendation_status_and_source_contract(tmp_path):
    config = RunConfig(
        start_date="2019-01-01",
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=True,
    )
    result = run_analysis(config)
    json_path = tmp_path / "run_results.json"
    write_run_results_json(result, json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    recommendation_status = payload["metadata"]["recommendation_status"]

    assert payload["metadata"]["current_recommendations_available"] is False
    assert payload["recommendations"]
    assert {row["recommendation_status"] for row in payload["recommendations"]} == {recommendation_status}
    assert {row["signal_date"] for row in payload["recommendations"]} == {payload["metadata"]["signal_date"]}
    assert payload["data_sources"]
    assert payload["price_sources"]
