import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import openpyxl
import pandas as pd

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.data import MarketData, generate_offline_sample_data
from momentum_factor_lab.report import write_pdf, write_reports
from momentum_factor_lab.workflow import run_analysis, write_run_results_json


LIQUIDITY_CAPACITY_COLUMNS = {
    "avg_share_volume_63d",
    "avg_dollar_volume_63d",
    "price_observations_63d",
    "volume_observations_63d",
    "dollar_volume_observations_63d",
    "min_liquidity_observations_required",
    "min_avg_volume_required",
    "min_avg_dollar_volume_required",
    "liquidity_evidence_status",
    "liquidity_filter_pass",
    "proposed_weight",
    "target_aum",
    "max_adv_participation",
    "target_notional",
    "max_trade_notional_by_adv",
    "capacity_notional_limit",
    "capacity_aum_limit",
    "adv_participation",
    "capacity_utilization",
    "capacity_status",
    "capacity_pass",
    "capacity_warning",
}


def _live_fixture_market_data(
    config: RunConfig,
    *,
    subset_run: bool,
    point_in_time: bool = False,
    requested_symbols: int | None = None,
    eligible_symbols: int | None = None,
) -> MarketData:
    sample_config = replace(
        config,
        offline_sample=True,
        end_date=datetime.now(UTC).date().isoformat(),
    )
    sample = generate_offline_sample_data(sample_config)
    candidate_symbols = len(sample.candidate_universe)
    if requested_symbols is None:
        requested_symbols = min(len(sample.prices.columns), config.max_price_symbols or len(sample.prices.columns)) if subset_run else len(sample.prices.columns)
    if eligible_symbols is None:
        eligible_symbols = len(sample.prices.columns)
    summary = pd.DataFrame(
        [
            {
                "source": "live-run-summary",
                "status": "partial_subset" if subset_run else "full_requested_universe",
                "records": len(sample.prices.columns),
                "candidate_symbols": candidate_symbols,
                "requested_price_symbols": requested_symbols,
                "eligible_price_symbols": eligible_symbols,
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
        target_aum=100_000,
        max_adv_participation=0.05,
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
    assert LIQUIDITY_CAPACITY_COLUMNS.issubset(result.recommendations.columns)
    assert result.recommendations["avg_share_volume_63d"].notna().all()
    assert result.recommendations["avg_dollar_volume_63d"].notna().all()
    assert result.recommendations["liquidity_evidence_status"].eq("pass").all()
    assert result.recommendations["capacity_status"].eq("pass").all()
    assert result.recommendations["target_notional"].gt(0).all()


def test_current_live_predeclared_exports_recommendations_key_and_sheet(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=100_000,
        max_adv_participation=0.05,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )

    result = write_reports(run_analysis(config))
    json_path = tmp_path / "run_results.json"
    write_run_results_json(result, json_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    workbook = openpyxl.load_workbook(result.output_paths["xlsx"], read_only=True)

    assert result.metadata["recommendation_output_key"] == "recommendations"
    assert "recommendations" in payload
    assert "research_signals" not in payload
    assert "recommendations" in workbook.sheetnames
    assert "research_signals" not in workbook.sheetnames


def test_stale_live_data_zeroes_recommendation_weights(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=1,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
    )
    market_data = _live_fixture_market_data(config, subset_run=False, point_in_time=True)
    market_data.as_of = pd.Timestamp("2020-01-01")
    monkeypatch.setattr("momentum_factor_lab.workflow.load_market_data", lambda _: market_data)

    result = run_analysis(config)

    assert result.metadata["recommendation_status"].startswith("stale_live_data_")
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()
    assert result.recommendations["recommendation_status"].eq(result.metadata["recommendation_status"]).all()
    assert result.recommendations["signal_date"].eq(str(market_data.prices.index.max().date())).all()


def test_missing_volume_data_has_explicit_liquidity_capacity_warning(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        min_avg_volume=0,
        min_avg_dollar_volume=0,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=100_000,
        max_adv_participation=0.05,
    )
    market_data = _live_fixture_market_data(config, subset_run=False, point_in_time=True)
    market_data.volumes = pd.DataFrame(index=market_data.prices.index)
    monkeypatch.setattr("momentum_factor_lab.workflow.load_market_data", lambda _: market_data)

    result = run_analysis(config)

    assert LIQUIDITY_CAPACITY_COLUMNS.issubset(result.recommendations.columns)
    assert result.recommendations["liquidity_evidence_status"].eq("missing_liquidity_evidence").all()
    assert not result.recommendations["liquidity_filter_pass"].any()
    assert result.recommendations["capacity_status"].eq("missing_or_failed_liquidity_evidence").all()
    assert "row_level_liquidity_pass" in result.metadata["tradability_blockers"]
    assert "capacity_estimated_and_pass" in result.metadata["tradability_blockers"]
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()


def test_sparse_liquidity_observations_block_tradable_output(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=100_000,
        max_adv_participation=0.05,
    )
    market_data = _live_fixture_market_data(config, subset_run=False, point_in_time=True)
    market_data.volumes.iloc[:-1, :] = pd.NA
    market_data.volumes.iloc[-1, :] = 1_000_000_000
    monkeypatch.setattr("momentum_factor_lab.workflow.load_market_data", lambda _: market_data)

    result = run_analysis(config)

    assert result.recommendations["volume_observations_63d"].eq(1).all()
    assert result.recommendations["liquidity_evidence_status"].eq("insufficient_liquidity_observations").all()
    assert "row_level_liquidity_pass" in result.metadata["tradability_blockers"]
    assert "capacity_estimated_and_pass" in result.metadata["tradability_blockers"]
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()


def test_live_tradable_output_requires_capacity_inputs(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )

    result = run_analysis(config)

    assert not result.metadata["current_recommendations_available"]
    assert "capacity_estimated_and_pass" in result.metadata["tradability_blockers"]
    assert result.recommendations["capacity_status"].eq("not_estimated_missing_aum_and_participation_limit").all()
    assert result.recommendations["weight"].eq(0.0).all()


def test_capacity_adv_participation_limit_blocks_tradable_output(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=10_000_000_000,
        max_adv_participation=0.0001,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )

    result = run_analysis(config)

    assert result.recommendations["liquidity_evidence_status"].eq("pass").all()
    assert result.recommendations["capacity_status"].eq("exceeds_adv_participation_limit").all()
    assert "capacity_estimated_and_pass" in result.metadata["tradability_blockers"]
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()


def test_small_user_universe_is_research_only_unless_approved_with_provenance(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=100_000,
        max_adv_participation=0.05,
        universe=["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN"],
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(config, subset_run=False, point_in_time=True),
    )

    result = run_analysis(config)

    assert len(result.market_data.candidate_universe) < result.config.min_tradable_universe_size
    assert not result.metadata["current_recommendations_available"]
    assert "broad_or_approved_tradable_universe" in result.metadata["tradability_blockers"]


def test_incomplete_requested_price_coverage_blocks_tradable_output(tmp_path, monkeypatch):
    config = RunConfig(
        output_dir=tmp_path / "outputs",
        report_dir=tmp_path / "reports",
        offline_sample=False,
        stale_after_days=10_000,
        top_n=5,
        max_weight=0.2,
        selected_factor="mom_1m",
        target_aum=100_000,
        max_adv_participation=0.05,
    )
    monkeypatch.setattr(
        "momentum_factor_lab.workflow.load_market_data",
        lambda _: _live_fixture_market_data(
            config,
            subset_run=False,
            point_in_time=True,
            requested_symbols=100,
            eligible_symbols=24,
        ),
    )

    result = run_analysis(config)

    assert "full_uncapped_price_universe" in result.metadata["tradability_blockers"]
    assert not result.metadata["current_recommendations_available"]
    assert result.recommendations["weight"].eq(0.0).all()


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
    output_key = payload["metadata"]["recommendation_output_key"]
    rows = payload[output_key]
    recommendation_status = payload["metadata"]["recommendation_status"]

    assert payload["metadata"]["current_recommendations_available"] is False
    assert output_key == "research_signals"
    assert rows
    assert LIQUIDITY_CAPACITY_COLUMNS.issubset(rows[0])
    assert {row["recommendation_status"] for row in rows} == {recommendation_status}
    assert {row["signal_date"] for row in rows} == {payload["metadata"]["signal_date"]}
    assert {row["capacity_status"] for row in rows} == {"not_estimated_missing_aum_and_participation_limit"}
    assert payload["data_sources"]
    assert payload["price_sources"]


def test_json_export_preserves_selected_turnover_cost_metadata(tmp_path):
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
    metadata = payload["metadata"]
    selected_metrics = result.metrics.loc[result.selected_factor]

    assert metadata["selected_factor_avg_turnover"] == selected_metrics["full_avg_turnover"]
    assert metadata["selected_factor_total_turnover"] == selected_metrics["full_total_turnover"]
    assert metadata["selected_factor_annualized_turnover"] == selected_metrics["full_annualized_turnover"]
    assert metadata["selected_factor_total_cost"] == selected_metrics["full_total_cost"]
    assert metadata["selected_factor_annualized_cost_drag"] == selected_metrics["full_annualized_cost_drag"]


def test_research_only_pdf_labels_output_as_research_signals_not_recommendations(tmp_path, monkeypatch):
    result = run_analysis(
        RunConfig(
            start_date="2019-01-01",
            output_dir=tmp_path / "outputs",
            report_dir=tmp_path / "reports",
            offline_sample=True,
        )
    )
    text_pages: list[tuple[str, list[str]]] = []
    table_titles: list[str] = []

    def capture_text_page(pdf, title, lines):
        text_pages.append((title, lines))

    def capture_table_page(pdf, title, frame, max_rows=18):
        table_titles.append(title)

    monkeypatch.setattr("momentum_factor_lab.report._text_page", capture_text_page)
    monkeypatch.setattr("momentum_factor_lab.report._table_page", capture_table_page)

    write_pdf(result, tmp_path / "report.pdf")

    executive_lines = "\n".join(text_pages[0][1])
    assert "Output type: Research signals (not tradable)" in executive_lines
    assert "Tradability blockers:" in executive_lines
    assert "Liquidity/capacity:" in executive_lines
    assert "Research signals (not tradable)" in table_titles
    assert "Current Top-20 Recommendations" not in table_titles


def test_report_exports_turnover_cost_diagnostic_columns(tmp_path):
    result = write_reports(
        run_analysis(
            RunConfig(
                start_date="2019-01-01",
                output_dir=tmp_path / "outputs",
                report_dir=tmp_path / "reports",
                offline_sample=True,
            )
        )
    )
    workbook = openpyxl.load_workbook(result.output_paths["xlsx"], read_only=True)
    headers = [cell.value for cell in next(workbook["backtest_metrics"].iter_rows(max_row=1))]

    assert {"full_total_turnover", "full_annualized_turnover", "full_total_cost", "full_annualized_cost_drag"}.issubset(headers)


def test_liquidity_capacity_thresholds_and_counts_are_exported(tmp_path):
    result = write_reports(
        run_analysis(
            RunConfig(
                start_date="2019-01-01",
                output_dir=tmp_path / "outputs",
                report_dir=tmp_path / "reports",
                offline_sample=True,
                min_avg_volume=123,
                min_avg_dollar_volume=456,
            )
        )
    )
    output_sheet = result.metadata["recommendation_output_sheet"]
    workbook = openpyxl.load_workbook(result.output_paths["xlsx"], read_only=True)
    headers = [cell.value for cell in next(workbook[output_sheet].iter_rows(max_row=1))]

    assert result.metadata["recommendation_liquidity_status_counts"]
    assert LIQUIDITY_CAPACITY_COLUMNS.issubset(headers)
    assert result.recommendations["min_avg_volume_required"].eq(123.0).all()
    assert result.recommendations["min_avg_dollar_volume_required"].eq(456.0).all()
    assert result.recommendations["capacity_warning"].str.contains("Capacity is not estimated").all()
