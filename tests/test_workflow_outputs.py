from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
import pandas as pd

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.data import MarketData, generate_offline_sample_data
from momentum_factor_lab.report import write_reports
from momentum_factor_lab.workflow import run_analysis


def _live_fixture_market_data(config: RunConfig, *, subset_run: bool, point_in_time: bool = False) -> MarketData:
    sample_config = replace(
        config,
        offline_sample=True,
        end_date=datetime.now(UTC).date().isoformat(),
    )
    sample = generate_offline_sample_data(sample_config)
    candidate_symbols = len(sample.candidate_universe)
    requested_symbols = min(len(sample.prices.columns), config.max_price_symbols or len(sample.prices.columns)) if subset_run else candidate_symbols + 1
    summary = pd.DataFrame(
        [
            {
                "source": "live-run-summary",
                "status": "partial_subset" if subset_run else "full_requested_universe",
                "records": len(sample.prices.columns),
                "candidate_symbols": candidate_symbols,
                "requested_price_symbols": requested_symbols,
                "eligible_price_symbols": len(sample.prices.columns),
                "excluded_symbols": 0,
                "subset_run": subset_run,
                "point_in_time_universe": point_in_time,
            }
        ]
    )
    return MarketData(
        prices=sample.prices,
        volumes=sample.volumes,
        provider="test-live-data",
        fetched_at=datetime.now(UTC),
        as_of=sample.prices.index.max(),
        exclusions=sample.exclusions,
        offline_sample=False,
        candidate_universe=sample.candidate_universe,
        eligible_universe=sample.eligible_universe,
        price_sources=sample.price_sources,
        data_sources=summary,
    )


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
        "research_signals",
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
    assert result.metadata["selected_factor_selection_source"] == "validation_performance"
    factor_sheet = workbook["factor_scores"]
    history_sheet = workbook["factor_score_history_top20"]
    assert factor_sheet.max_row > len(result.market_data.prices.columns)
    assert history_sheet.max_row < 1_048_576


def test_live_failure_or_offline_status_never_claims_current(tmp_path, monkeypatch):
    config = RunConfig(output_dir=tmp_path / "outputs", report_dir=tmp_path / "reports", offline_sample=True)
    result = run_analysis(config)
    assert result.metadata["recommendation_status"] != "current_live"
    assert not result.metadata["current_recommendations_available"]


def test_subset_live_run_is_research_only_with_zero_tradable_weights(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        max_price_symbols=8,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=True),
    )

    result = write_reports(run_analysis(config))

    assert "subset_run" in result.metadata["recommendation_status"]
    assert not result.metadata["current_recommendations_available"]
    assert not result.metadata["tradable_recommendations_available"]
    assert result.metadata["recommendation_output_key"] == "research_signals"
    assert result.metadata["research_only"]
    assert "full_uncapped_price_universe" in result.metadata["tradability_blockers"]
    assert result.recommendations["weight"].sum() == 0.0
    assert set(result.recommendations["recommendation_output"]) == {"research_signals"}
    workbook = openpyxl.load_workbook(result.output_paths["xlsx"], read_only=True)
    assert "research_signals" in workbook.sheetnames
    assert "recommendations" not in workbook.sheetnames


def test_full_live_run_without_point_in_time_evidence_is_research_only(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=False),
    )

    result = run_analysis(config)

    assert "research_only_missing" in result.metadata["recommendation_status"]
    assert not result.metadata["current_recommendations_available"]
    assert "point_in_time_universe" in result.metadata["tradability_blockers"]
    assert result.metadata["recommendation_output_key"] == "research_signals"
    assert result.recommendations["weight"].sum() == 0.0


def test_fresh_live_run_requires_predeclared_factor_for_current_recommendations(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )

    result = run_analysis(config)

    assert result.metadata["selected_factor_selection_source"] == "validation_performance"
    assert "research_only_missing" in result.metadata["recommendation_status"]
    assert not result.metadata["current_recommendations_available"]
    assert not result.metadata["tradable_recommendations_available"]
    assert "predeclared_selected_factor" in result.metadata["tradability_blockers"]
    assert result.recommendations["weight"].eq(0.0).all()


def test_predeclared_factor_controls_fresh_live_recommendations_not_validation_rank(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
    )

    def rank_other_factor_first(metrics):
        ranked = metrics.assign(composite_score=0.0)[["composite_score"]]
        ranked.loc["mom_12_1", "composite_score"] = 1.0
        return ranked.sort_values("composite_score", ascending=False)

    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )
    monkeypatch.setattr("momentum_factor_lab.workflow._score_factors", rank_other_factor_first)

    result = run_analysis(config)

    assert result.metadata["validation_selected_factor"] == "mom_12_1"
    assert result.selected_factor == "mom_1m"
    assert result.metadata["selected_factor_selection_source"] == "predeclared"
    assert result.metadata["recommendation_status"] == "current_live"
    assert result.metadata["current_recommendations_available"]
    assert result.metadata["tradable_recommendations_available"]
    assert result.metadata["tradability_blockers"] == []
    assert result.recommendations["selected_factor"].eq("mom_1m").all()
    assert result.recommendations["selected_factor_selection_source"].eq("predeclared").all()
