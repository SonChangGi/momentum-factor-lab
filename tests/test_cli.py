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
                "recommendation_output_key": "research_signals",
                "selected_factor": config.selected_factor,
                "recommendation_status": "current_live_research_only_missing_test",
                "current_recommendations_available": False,
                "fresh_live_data_available": True,
                "recommendation_output_label": "Research signals (not tradable)",
                "data_as_of": "2026-06-05",
                "provider": "test",
                "candidate_universe_size": 6,
                "eligible_price_universe_size": 6,
                "factor_count": 22,
                "factor_validation_status": "pass",
                "selected_factor_selection_source": "predeclared",
                "tradability_blockers": ["test"],
                "recommendation_capacity_warning": "test warning",
            },
            output_paths={"json": str(tmp_path / "run.json")},
            recommendations=pd.DataFrame([{"rank": 1, "symbol": "SPY", "weight": 0.0}]),
        )

    monkeypatch.setattr(cli, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(cli, "write_reports", lambda result: result)

    args = cli.build_parser().parse_args(
        [
            "run",
            "--live",
            "--universe",
            "SPY,QQQ,AAPL,MSFT,NVDA,AMZN",
            "--selected-factor",
            "mom_1m",
            "--target-aum",
            "100000",
            "--max-adv-participation",
            "0.05",
            "--point-in-time-universe-provenance",
            "test PIT source as-of 2026-06-05",
            "--approved-tradable-universe",
            "--min-tradable-universe-size",
            "6",
            "--min-liquidity-observations",
            "42",
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
    assert config.target_aum == 100_000
    assert config.max_adv_participation == 0.05
    assert config.point_in_time_universe_provenance == "test PIT source as-of 2026-06-05"
    assert config.approved_tradable_universe
    assert config.min_tradable_universe_size == 6
    assert config.min_liquidity_observations == 42
