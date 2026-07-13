from pathlib import Path

import pytest

from momentum_factor_lab.config import MAX_TOP_N, RunConfig, WEIGHTING_POLICIES


def test_default_research_contract_has_four_fixed_policies_and_explicit_scores() -> None:
    config = RunConfig(demo=True)
    config.validate()

    assert config.demo_symbol_count == 200
    assert config.benchmark == "SPY"
    assert config.chart_benchmark == "^IXIC"
    assert config.additional_comparison_benchmarks == ("QQQ",)
    assert config.comparison_benchmarks == ("SPY", "^IXIC", "QQQ")
    assert config.demo_missing_ratio == 0.0
    assert config.top_n == 20
    assert config.evaluation_window_days == 756
    assert config.min_valuation_coverage == 0.98
    assert config.min_daily_risk_observations == 504
    assert (
        config.weighting_policies
        == WEIGHTING_POLICIES
        == (
            "equal_weight",
            "capped_linear_rank",
            "capped_vol_adjusted_rank",
            "score_liquidity_rank",
        )
    )
    assert config.score_weights == {
        "sortino": 0.25,
        "calmar": 0.20,
        "max_drawdown": 0.20,
        "cagr": 0.15,
        "sharpe": 0.10,
        "stability": 0.10,
    }
    assert sum(config.score_weights.values()) == pytest.approx(1.0)
    assert (
        config.score_liquidity_score_weight + config.score_liquidity_liquidity_weight
        == pytest.approx(1.0)
    )
    assert config.joint_selection_version == "joint-factor-policy-v1"
    assert config.absolute_guardrail_version == "absolute-factor-policy-v1"
    assert config.analysis_cache_version == "analysis-cache-v1"
    assert config.selection_min_sharpe == 0.0
    assert config.selection_max_drawdown == pytest.approx(0.60)
    assert config.selection_max_annualized_cost_drag == pytest.approx(0.02)
    assert config.selection_min_effective_names == pytest.approx(10.0)
    assert config.selection_max_target_hhi == pytest.approx(0.15)
    assert config.selection_max_target_weight == pytest.approx(0.15)
    assert config.selection_max_abs_security_day_contribution == pytest.approx(0.10)
    assert config.selection_max_security_absolute_contribution_share == pytest.approx(0.35)
    assert config.selection_max_leave_one_security_cagr_delta == pytest.approx(0.25)
    assert config.selection_extreme_event_action == "exclude"
    assert config.selection_extreme_event_penalty_points == pytest.approx(20.0)
    assert config.market_cache_max_age_hours == pytest.approx(24.0)
    assert config.refresh_market_data is False
    serialized = config.to_dict()
    assert serialized["joint_selection_version"] == config.joint_selection_version
    assert serialized["absolute_guardrail_version"] == config.absolute_guardrail_version
    assert serialized["analysis_cache_version"] == config.analysis_cache_version
    assert serialized["comparison_benchmarks"] == ["SPY", "^IXIC", "QQQ"]
    assert serialized["score_liquidity_score_weight"] == pytest.approx(0.60)
    assert serialized["selection_max_security_absolute_contribution_share"] == pytest.approx(0.35)
    assert "score_size_market_cap_weight" not in serialized
    assert "policy_sharpe_tolerance" not in serialized


def test_exactly_one_live_local_or_demo_source_is_required() -> None:
    with pytest.raises(ValueError, match="choose exactly one"):
        RunConfig().validate()
    with pytest.raises(ValueError, match="choose exactly one"):
        RunConfig(demo=True, prices_path=Path("prices.csv")).validate()
    with pytest.raises(ValueError, match="choose exactly one"):
        RunConfig(live=True, demo=True).validate()

    RunConfig(live=True).validate()
    RunConfig(demo=True).validate()
    RunConfig(prices_path=Path("prices.csv")).validate()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"demo_symbol_count": 49}, "demo_symbol_count"),
        ({"demo_seed": -1}, "demo_seed"),
        ({"demo_missing_ratio": -0.01}, "demo_missing_ratio"),
        ({"demo_missing_ratio": 0.0009}, "at least 0.001"),
        ({"demo_missing_ratio": 1.0}, "demo_missing_ratio"),
        ({"top_n": 0}, "top_n"),
        ({"top_n": MAX_TOP_N + 1}, "top_n"),
        ({"top_n": True}, "top_n"),
        ({"max_weight": 0.0}, "max_weight"),
        ({"min_evaluation_observations": 200}, "min_evaluation_observations"),
        ({"score_winsor_lower": 0.9, "score_winsor_upper": 0.1}, "winsor"),
        ({"score_sortino_weight": 0.30}, "sum to 1"),
    ],
)
def test_invalid_research_configuration_is_rejected(
    changes: dict[str, object],
    message: str,
) -> None:
    config = RunConfig(demo=True, **changes)
    with pytest.raises(ValueError, match=message):
        config.validate()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"weighting_policies": WEIGHTING_POLICIES[:-1]},
            "all four canonical weighting policies",
        ),
        (
            {"weighting_policies": tuple(reversed(WEIGHTING_POLICIES))},
            "fixed order",
        ),
        ({"min_volatility_observations": 1}, "fit the volatility lookback"),
        (
            {"volatility_lookback_days": 10, "min_volatility_observations": 11},
            "fit the volatility lookback",
        ),
        ({"volatility_floor": 0.0}, "volatility bounds"),
        (
            {"volatility_floor": 0.50, "volatility_cap": 0.40},
            "volatility bounds",
        ),
        ({"score_liquidity_score_weight": 0.70}, "sum to 1"),
        (
            {
                "score_liquidity_score_weight": 1.10,
                "score_liquidity_liquidity_weight": -0.10,
            },
            "non-negative and sum to 1",
        ),
        ({"score_liquidity_rank_floor": -0.01}, "rank_floor"),
        ({"selection_min_effective_names": 0.0}, "must be positive"),
        (
            {"top_n": 5, "selection_min_effective_names": 6.0},
            "cannot exceed top_n",
        ),
        ({"selection_min_sharpe": -10.01}, "at least -10"),
        ({"selection_max_drawdown": 0.0}, "must be in"),
        ({"selection_max_drawdown": 1.01}, "must be in"),
        ({"selection_max_annualized_cost_drag": -0.01}, "must be non-negative"),
        ({"selection_max_target_hhi": 0.0}, "must be in"),
        ({"selection_max_target_weight": 1.01}, "must be in"),
        (
            {"selection_max_abs_security_day_contribution": -0.01},
            "must be non-negative",
        ),
        (
            {"selection_max_security_absolute_contribution_share": 1.01},
            "must be in",
        ),
        (
            {"selection_max_leave_one_security_cagr_delta": -0.01},
            "must be non-negative",
        ),
        (
            {"selection_extreme_event_penalty_points": -0.01},
            "must be non-negative",
        ),
        ({"selection_extreme_event_action": "fallback"}, "warn, penalize, or exclude"),
        ({"market_cache_max_age_hours": 0.0}, "must be positive"),
        ({"min_valuation_coverage": 0.0}, "min_valuation_coverage"),
        ({"min_valuation_coverage": 1.01}, "min_valuation_coverage"),
        ({"min_daily_risk_observations": 1}, "min_daily_risk_observations"),
        (
            {
                "evaluation_window_days": 252,
                "min_evaluation_observations": 252,
                "min_daily_risk_observations": 253,
            },
            "min_daily_risk_observations",
        ),
    ],
)
def test_policy_and_coverage_guardrails_are_fail_closed(
    changes: dict[str, object],
    message: str,
) -> None:
    config = RunConfig(demo=True, **changes)
    with pytest.raises(ValueError, match=message):
        config.validate()


def test_config_exposes_live_mode_without_credentials_or_execution_contracts() -> None:
    fields = set(RunConfig.__dataclass_fields__)
    assert {
        "live",
        "weighting_policies",
        "min_valuation_coverage",
        "score_liquidity_score_weight",
        "score_liquidity_liquidity_weight",
        "selection_min_sharpe",
        "selection_max_drawdown",
        "selection_max_abs_security_day_contribution",
        "selection_max_security_absolute_contribution_share",
        "selection_max_leave_one_security_cagr_delta",
    }.issubset(fields)
    forbidden = {
        "api_key",
        "api_secret",
        "broker",
        "order_api",
        "report_dir",
        "pdf",
        "xlsx",
        "score_size_score_weight",
        "score_size_market_cap_weight",
        "score_size_liquidity_weight",
        "policy_sharpe_tolerance",
        "policy_mdd_tolerance",
        "policy_max_cost_drag",
        "policy_min_effective_n",
    }
    assert forbidden.isdisjoint(fields)


def test_cash_return_at_or_below_total_loss_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than -1"):
        RunConfig(demo=True, annual_cash_return=-1.0).validate()


def test_local_volume_requires_explicit_split_adjusted_basis() -> None:
    with pytest.raises(ValueError, match="volume-basis split_adjusted"):
        RunConfig(
            prices_path=Path("prices.csv"),
            volumes_path=Path("volumes.csv"),
        ).validate()
    RunConfig(
        prices_path=Path("prices.csv"),
        volumes_path=Path("volumes.csv"),
        volume_basis="split_adjusted",
    ).validate()


def test_live_mode_owns_its_price_and_volume_basis() -> None:
    with pytest.raises(ValueError, match="volume_basis requires a volume file"):
        RunConfig(live=True, volume_basis="split_adjusted").validate()


def test_demo_missing_ratio_is_demo_only_and_accepts_sparse_boundary() -> None:
    RunConfig(demo=True, demo_missing_ratio=0.001).validate()
    with pytest.raises(ValueError, match="requires --demo"):
        RunConfig(
            prices_path=Path("prices.csv"),
            demo_missing_ratio=0.001,
        ).validate()


def test_invalid_benchmark_symbol_is_rejected() -> None:
    with pytest.raises(ValueError, match="supported security symbol"):
        RunConfig(demo=True, benchmark="BAD SYMBOL").validate()


def test_comparison_benchmarks_are_normalized_validated_and_deduplicated() -> None:
    config = RunConfig(
        demo=True,
        benchmark=" spy ",
        chart_benchmark=" ^ixic ",
        additional_comparison_benchmarks=(" qqq ", "QQQ", "spy", "^IXIC", "dia"),
    )
    config.validate()

    assert config.additional_comparison_benchmarks == ("QQQ", "DIA")
    assert config.comparison_benchmarks == ("SPY", "^IXIC", "QQQ", "DIA")

    with pytest.raises(ValueError, match="additional_comparison_benchmarks"):
        RunConfig(demo=True, additional_comparison_benchmarks=("BAD SYMBOL",)).validate()
