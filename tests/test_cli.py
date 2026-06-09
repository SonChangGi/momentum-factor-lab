from types import SimpleNamespace

import pandas as pd

from momentum_factor_lab import cli


def test_cli_wires_tradability_gate_inputs(monkeypatch, tmp_path):
    captured = {}

    def fake_run_analysis(config):
        captured["config"] = config
        return SimpleNamespace(
            config=config,
            selected_factor=config.selected_factor,
            metadata={
                "recommendation_output_key": "recommendations",
                "selected_factor": config.selected_factor,
                "recommendation_status": "current_live_with_limitations_test",
                "current_recommendations_available": True,
                "fresh_live_data_available": True,
                "recommendation_output_label": "Practical recommendations",
                "data_as_of": "2026-06-05",
                "provider": "test",
                "candidate_universe_size": 6,
                "eligible_price_universe_size": 6,
                "factor_count": 22,
                "factor_validation_status": "pass",
                "universe_profile": config.universe_profile,
                "factor_selection_mode": config.effective_factor_selection_mode,
                "selected_factor_selection_source": "predeclared",
                "same_sample_selection_blocked_for_tradable": False,
                "decision_support_tier": "practical_recommendations",
                "fail_closed": False,
                "fail_closed_reasons": [],
                "tradability_blockers": [],
                "execution_limitations": ["test"],
                "data_quality_gate": {"manifest_available": True, "recommendation_rows_pass": False},
                "data_quality_status_counts": {"pass": 5},
                "recommendation_data_quality_status_counts": {"pass": 1},
                "recommendation_capacity_warning": "test warning",
                "recommendation_weighting_method": config.recommendation_weighting_method,
                "recommendation_weight_sum": 1.0,
                "recommendation_cash_weight": 0.0,
            },
            output_paths={"json": str(tmp_path / "run.json")},
            recommendations=pd.DataFrame([{"rank": 1, "symbol": "SPY", "weight": 1.0}]),
        )

    monkeypatch.setattr(cli, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(cli, "write_reports", lambda result: result)

    args = cli.build_parser().parse_args(
        [
            "run",
            "--live",
            "--universe",
            "SPY,QQQ,AAPL,MSFT,NVDA,AMZN",
            "--universe-profile",
            "aggressive_stock_only",
            "--universe-source-mode",
            "refresh",
            "--selected-factor",
            "mom_1m",
            "--factor-selection-mode",
            "predeclared",
            "--selection-window",
            "policy-v1",
            "--frozen-policy-path",
            str(tmp_path / "policy.json"),
            "--cost-stress-high-bps",
            "75",
            "--sec-user-agent",
            "momentum-factor-lab-test contact@example.com",
            "--target-aum",
            "100000",
            "--max-adv-participation",
            "0.05",
            "--recommendation-weighting-method",
            "score_size_liquidity",
            "--recommendation-score-weight",
            "0.5",
            "--recommendation-market-cap-weight",
            "0.3",
            "--recommendation-liquidity-weight",
            "0.2",
            "--recommendation-rank-floor",
            "0.04",
            "--disable-recommendation-market-cap-lookup",
            "--stooq-fallback-limit",
            "11",
            "--finance-datareader-fallback-limit",
            "12",
            "--point-in-time-universe-provenance",
            "source=test-cli as_of=2026-06-05 symbol_count=6 hash=fixture",
            "--approved-tradable-universe",
            "--min-tradable-universe-size",
            "6",
            "--min-liquidity-observations",
            "42",
            "--data-quality-lookback-days",
            "126",
            "--max-price-missing-ratio",
            "0.02",
            "--max-volume-missing-ratio",
            "0.03",
            "--max-extreme-daily-return",
            "0.45",
            "--output-dir",
            str(tmp_path / "outputs"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--json",
        ]
    )

    summary = cli.run_command(args)
    config = captured["config"]

    assert summary["fresh_live_data_available"]
    assert summary["universe_profile"] == "aggressive_stock_only"
    assert summary["factor_selection_mode"] == "predeclared"
    assert not summary["same_sample_selection_blocked_for_tradable"]
    assert summary["decision_support_tier"] == "practical_recommendations"
    assert not summary["fail_closed"]
    assert summary["execution_limitations"] == ["test"]
    assert summary["data_quality_gate"]["manifest_available"]
    assert config.universe_profile == "aggressive_stock_only"
    assert config.universe_source_mode == "refresh"
    assert config.factor_selection_mode == "predeclared"
    assert config.selection_window == "policy-v1"
    assert config.frozen_policy_path == tmp_path / "policy.json"
    assert config.cost_stress_high_bps == 75
    assert config.sec_user_agent == "momentum-factor-lab-test contact@example.com"
    assert config.target_aum == 100_000
    assert config.max_adv_participation == 0.05
    assert config.recommendation_weighting_method == "score_size_liquidity"
    assert config.recommendation_score_weight == 0.5
    assert config.recommendation_market_cap_weight == 0.3
    assert config.recommendation_liquidity_weight == 0.2
    assert config.recommendation_rank_floor == 0.04
    assert not config.recommendation_market_cap_lookup
    assert config.stooq_fallback_limit == 11
    assert config.finance_datareader_fallback_limit == 12
    assert config.point_in_time_universe_provenance == "source=test-cli as_of=2026-06-05 symbol_count=6 hash=fixture"
    assert config.approved_tradable_universe
    assert config.min_tradable_universe_size == 6
    assert config.min_liquidity_observations == 42
    assert config.data_quality_lookback_days == 126
    assert config.max_price_missing_ratio == 0.02
    assert config.max_volume_missing_ratio == 0.03
    assert config.max_extreme_daily_return == 0.45


def _install_fake_reports(monkeypatch, tmp_path, captured):
    def fake_run_analysis(config):
        captured["config"] = config
        return SimpleNamespace(
            config=config,
            selected_factor=config.selected_factor or "mom_12_1",
            metadata={
                "recommendation_output_key": "recommendations",
                "selected_factor": config.selected_factor or "mom_12_1",
                "recommendation_status": "sample_offline_not_current",
                "current_recommendations_available": False,
                "fresh_live_data_available": False,
                "recommendation_output_label": "Reference recommendations (not current)",
                "data_as_of": config.effective_end_date,
                "provider": "test-provider",
                "candidate_universe_size": len(config.universe),
                "eligible_price_universe_size": 3,
                "factor_count": 55,
                "factor_validation_status": "pass",
                "universe_profile": config.universe_profile,
                "factor_selection_mode": config.effective_factor_selection_mode,
                "selected_factor_selection_source": "research_validation",
                "same_sample_selection_blocked_for_tradable": False,
                "decision_support_tier": "non_current_reference",
                "fail_closed": True,
                "fail_closed_reasons": ["fresh_live_data"],
                "tradability_blockers": ["fresh_live_data"],
                "execution_limitations": ["fresh_live_data"],
                "data_quality_gate": {"manifest_available": True, "recommendation_rows_pass": True},
                "data_quality_status_counts": {"pass": 3},
                "recommendation_data_quality_status_counts": {"pass": 3},
                "recommendation_capacity_warning": "test warning",
                "recommendation_weighting_method": config.recommendation_weighting_method,
                "recommendation_weight_sum": 0.0,
                "recommendation_cash_weight": 1.0,
            },
            output_paths={"json": str(tmp_path / "run.json")},
            recommendations=pd.DataFrame(
                [
                    {"rank": 1, "symbol": "AAPL", "weight": 0.0},
                    {"rank": 2, "symbol": "MSFT", "weight": 0.0},
                    {"rank": 3, "symbol": "NVDA", "weight": 0.0},
                ]
            ),
        )

    monkeypatch.setattr(cli, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(cli, "write_reports", lambda result: result)


def _feed_inputs(monkeypatch, values):
    iterator = iter(values)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(iterator, ""))


def test_wizard_parser_aliases_are_additive():
    parser = cli.build_parser()
    assert parser.parse_args(["wizard"]).command == "wizard"
    assert parser.parse_args(["run-wizard"]).command == "run-wizard"
    assert parser.parse_args(["interactive"]).command == "interactive"
    run_args = parser.parse_args(["run", "--top-n", "7"])
    assert run_args.command == "run"
    assert run_args.top_n == 7


def test_wizard_defaults_show_descriptions_and_use_existing_pipeline(monkeypatch, tmp_path, capsys):
    captured = {}
    _install_fake_reports(monkeypatch, tmp_path, captured)
    _feed_inputs(monkeypatch, [""] * 32)

    assert cli.main(["wizard", "--no-confirm"]) == 0

    config = captured["config"]
    assert config.start_date == "2016-01-01"
    assert config.end_date is None
    assert config.top_n == 20
    assert config.max_weight == 0.10
    assert str(config.output_dir) == "outputs/sample"
    assert str(config.report_dir) == "reports/sample"
    assert config.offline_sample
    output = capsys.readouterr().out
    assert "Top-N holdings" in output
    assert "Default [20]" in output
    assert "Choices:" in output
    assert "Run configuration review" in output


def test_wizard_custom_inputs_and_invalid_reprompts(monkeypatch, tmp_path):
    captured = {}
    _install_fake_reports(monkeypatch, tmp_path, captured)
    _feed_inputs(
        monkeypatch,
        [
            "live",
            "2018-01-02",
            "2026-06-08",
            "0",
            "5",
            "2",
            "0.2",
            str(tmp_path / "out"),
            str(tmp_path / "reports"),
            str(tmp_path / "cache"),
            "aapl, msft, nvda",
            "bad_profile",
            "extended_current",
            "refresh",
            "abc",
            "25",
            "1000000",
            "0.05",
            "3.5",
            "2500000",
            "126",
            "n",
        ],
    )

    assert cli.main(["wizard", "--no-confirm"]) == 0

    config = captured["config"]
    assert not config.offline_sample
    assert config.start_date == "2018-01-02"
    assert config.end_date == "2026-06-08"
    assert config.top_n == 5
    assert config.max_weight == 0.2
    assert config.output_dir == tmp_path / "out"
    assert config.report_dir == tmp_path / "reports"
    assert config.cache_dir == tmp_path / "cache"
    assert config.universe == ["AAPL", "MSFT", "NVDA"]
    assert config.universe_profile == "extended_current"
    assert config.universe_source_mode == "refresh"
    assert config.max_price_symbols == 25
    assert config.target_aum == 1_000_000
    assert config.max_adv_participation == 0.05
    assert config.min_price == 3.5
    assert config.min_avg_dollar_volume == 2_500_000
    assert config.min_history_days == 126


def test_wizard_cross_field_validation_exits_before_analysis(monkeypatch):
    called = False

    def fail_run_analysis(_config):
        nonlocal called
        called = True
        raise AssertionError("run_analysis should not be called")

    monkeypatch.setattr(cli, "run_analysis", fail_run_analysis)
    _feed_inputs(monkeypatch, ["", "2026-06-08", "2026-01-01"] + [""] * 32)

    try:
        cli.main(["wizard", "--no-confirm"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - defensive
        raise AssertionError("expected parser-style exit")
    assert not called


def test_wizard_eof_exits_before_analysis(monkeypatch):
    called = False

    def fail_run_analysis(_config):
        nonlocal called
        called = True
        raise AssertionError("run_analysis should not be called")

    monkeypatch.setattr(cli, "run_analysis", fail_run_analysis)

    def raise_eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    try:
        cli.main(["wizard"])
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover - defensive
        raise AssertionError("expected abort exit")
    assert not called


def test_wizard_offline_smoke_creates_selected_artifacts(monkeypatch, tmp_path):
    output_dir = tmp_path / "wizard-outputs"
    report_dir = tmp_path / "wizard-reports"
    _feed_inputs(
        monkeypatch,
        [
            "offline_sample",
            "2024-01-01",
            "2024-12-31",
            "5",
            "0.2",
            str(output_dir),
            str(report_dir),
            str(tmp_path / "cache"),
            "",
            "large_liquid",
            "packaged",
            "",
            "",
            "",
            "5",
            "1000000",
            "63",
            "n",
        ],
    )

    assert cli.main(["wizard", "--no-confirm"]) == 0

    assert list(output_dir.glob("run_results_*.json"))
    assert list(report_dir.glob("momentum_factor_report_*.pdf"))
    assert list(report_dir.glob("momentum_factor_analysis_*.xlsx"))
