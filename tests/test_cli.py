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
