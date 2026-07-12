import numpy as np
import pandas as pd
import pytest

from momentum_factor_lab.config import RunConfig, WEIGHTING_POLICIES
from momentum_factor_lab.portfolio import (
    TIE_BREAK_POLICY,
    balanced_weights,
    construct_model_portfolio,
    construct_target_allocation,
)


SIGNAL_DATE = pd.Timestamp("2025-12-31")


def _config(*, top_n: int = 4, max_weight: float = 0.40) -> RunConfig:
    return RunConfig(
        demo=True,
        demo_symbol_count=50,
        top_n=top_n,
        max_weight=max_weight,
        selection_min_effective_names=min(2.0, float(top_n)),
    )


def _policy_inputs() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    index = pd.Index(["AAA", "BBB", "CCC", "DDD"])
    scores = pd.Series([4.0, 3.0, 2.0, 1.0], index=index)
    prices = pd.Series([10.0, 20.0, 30.0, 40.0], index=index)
    eligibility = pd.Series(True, index=index)
    trailing_volatility = pd.Series(1.0, index=index)
    trailing_dollar_volume = pd.Series([4.0, 3.0, 2.0, 1.0], index=index)
    return scores, prices, eligibility, trailing_volatility, trailing_dollar_volume


@pytest.mark.parametrize(
    ("policy_id", "expected_weights"),
    [
        ("equal_weight", [0.25, 0.25, 0.25, 0.25]),
        ("capped_linear_rank", [0.40, 0.30, 0.20, 0.10]),
        ("capped_vol_adjusted_rank", [0.40, 0.30, 0.20, 0.10]),
        (
            "score_liquidity_rank",
            [1.05 / 2.70, 0.80 / 2.70, 0.55 / 2.70, 0.30 / 2.70],
        ),
    ],
)
def test_four_policy_golden_weights(
    policy_id: str,
    expected_weights: list[float],
) -> None:
    scores, prices, eligibility, volatility, liquidity = _policy_inputs()

    result = construct_target_allocation(
        policy_id,
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        _config(),
        trailing_volatility=volatility,
        trailing_dollar_volume=liquidity,
    )

    assert result.status == "available"
    assert result.rows["symbol"].tolist() == ["AAA", "BBB", "CCC", "DDD"]
    assert result.rows["weight"].tolist() == pytest.approx(expected_weights)
    assert result.cash_weight == pytest.approx(0.0)
    assert result.policy_id == policy_id
    assert result.policy_version == "1"


def test_linear_rank_uses_average_rank_strength_for_equal_factor_scores() -> None:
    scores = pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 2.0})
    inputs = {
        "prices": pd.Series(10.0, index=scores.index),
        "eligibility": pd.Series(True, index=scores.index),
        "liquidity": pd.Series({"AAA": 30.0, "BBB": 20.0, "CCC": 10.0}),
    }

    result = construct_target_allocation(
        "capped_linear_rank",
        SIGNAL_DATE,
        scores,
        inputs["prices"],
        inputs["eligibility"],
        _config(top_n=3, max_weight=1.0),
        trailing_dollar_volume=inputs["liquidity"],
    )

    rows = result.rows.set_index("symbol")
    assert rows.loc["AAA", "rankComponent"] == pytest.approx(3.0)
    assert rows.loc["BBB", "rankComponent"] == pytest.approx(1.5)
    assert rows.loc["CCC", "rankComponent"] == pytest.approx(1.5)
    assert rows.loc["BBB", "weight"] == pytest.approx(rows.loc["CCC", "weight"])
    assert rows["weight"].tolist() == pytest.approx([0.5, 0.25, 0.25])


def test_top_n_boundary_tie_uses_trailing_dollar_volume_then_symbol() -> None:
    scores = pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 2.0, "DDD": 2.0})
    prices = pd.Series(10.0, index=scores.index)
    eligibility = pd.Series(True, index=scores.index)
    # CCC and DDD have the same best boundary liquidity; symbol ascending selects CCC.
    liquidity = pd.Series({"AAA": 1.0, "BBB": 10.0, "CCC": 20.0, "DDD": 20.0})

    result = construct_target_allocation(
        "equal_weight",
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        _config(top_n=2, max_weight=0.50),
        trailing_dollar_volume=liquidity,
    )

    assert result.status == "available"
    assert result.rows["symbol"].tolist() == ["AAA", "CCC"]
    assert result.rows["weight"].tolist() == pytest.approx([0.5, 0.5])
    assert "top_n_boundary_tie_resolved_by_trailing_dollar_volume" in result.reasons
    assert result.component_status["selectionTieBreak"] == (
        "trailing_dollar_volume_desc_then_symbol_asc"
    )
    assert result.tie_break_policy == TIE_BREAK_POLICY


def test_boundary_tie_without_enough_liquidity_is_unavailable_not_arbitrary() -> None:
    scores = pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 2.0, "DDD": 2.0})
    prices = pd.Series(10.0, index=scores.index)
    eligibility = pd.Series(True, index=scores.index)

    result = construct_target_allocation(
        "equal_weight",
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        _config(top_n=2, max_weight=0.50),
        trailing_dollar_volume=pd.Series(np.nan, index=scores.index),
    )

    assert result.status == "unavailable"
    assert result.cash_weight == 1.0
    assert result.reasons == ["top_n_boundary_tie_has_no_finite_liquidity_tie_break"]


@pytest.mark.parametrize("policy_id", WEIGHTING_POLICIES)
def test_all_policies_respect_caps_cash_and_weight_invariants(policy_id: str) -> None:
    scores, prices, eligibility, volatility, liquidity = _policy_inputs()
    config = _config(top_n=3, max_weight=0.20)

    result = construct_target_allocation(
        policy_id,
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        config,
        trailing_volatility=volatility,
        trailing_dollar_volume=liquidity,
    )

    weights = result.rows["weight"]
    assert result.status == "available"
    assert len(weights) == 3
    assert np.isfinite(weights).all()
    assert weights.ge(0.0).all()
    assert weights.le(config.max_weight + 1e-12).all()
    assert weights.sum() == pytest.approx(0.60)
    assert result.cash_weight == pytest.approx(0.40)
    assert weights.sum() + result.cash_weight == pytest.approx(1.0)
    assert result.concentration["maxWeight"] <= config.max_weight + 1e-12
    assert result.concentration["cashWeight"] == pytest.approx(result.cash_weight)
    assert "max_weight_capacity_or_missing_policy_inputs" in result.reasons


def test_score_liquidity_policy_uses_only_score_and_trailing_liquidity() -> None:
    scores, prices, eligibility, volatility, liquidity = _policy_inputs()
    result = construct_target_allocation(
        "score_liquidity_rank",
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        _config(),
        trailing_volatility=volatility,
        trailing_dollar_volume=liquidity,
    )

    assert result.status == "available"
    assert result.component_status["score"] == "available"
    assert result.component_status["liquidity"] == "trailing_raw_dollar_volume"
    assert "size" not in result.component_status
    assert "sizeComponent" not in result.rows
    assert result.rows["weight"].tolist() == pytest.approx(
        [1.05 / 2.70, 0.80 / 2.70, 0.55 / 2.70, 0.30 / 2.70]
    )


@pytest.mark.parametrize("policy_id", WEIGHTING_POLICIES)
def test_current_model_portfolio_is_an_exact_wrapper_of_target_kernel(policy_id: str) -> None:
    scores, prices, eligibility, volatility, liquidity = _policy_inputs()
    config = _config()
    target = construct_target_allocation(
        policy_id,
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        config,
        trailing_volatility=volatility,
        trailing_dollar_volume=liquidity,
    )
    current = construct_model_portfolio(
        "mom",
        SIGNAL_DATE,
        scores,
        prices,
        eligibility,
        config,
        policy_id=policy_id,
        trailing_volatility=volatility,
        trailing_dollar_volume=liquidity,
        names=pd.Series({symbol: f"Name {symbol}" for symbol in scores.index}),
    )

    assert current.status == target.status == "available"
    assert current.allocation.policy_id == target.policy_id == policy_id
    assert current.rows["symbol"].tolist() == target.rows["symbol"].tolist()
    assert current.rows["weight"].tolist() == pytest.approx(target.rows["weight"].tolist())
    assert current.cash_weight == pytest.approx(target.cash_weight)
    assert current.to_dict()["targetType"] == "current_research_target"
    assert current.to_dict()["executionTiming"] == ("next_available_session_close_after_signal")


def test_balanced_weights_are_ranked_capped_and_leave_explicit_cash() -> None:
    scores = pd.Series({"C": 1.0, "A": 3.0, "B": 2.0, "D": 0.0})
    weights = balanced_weights(scores, top_n=3, max_weight=0.20)

    assert weights.loc[["A", "B", "C"]].tolist() == pytest.approx([0.20] * 3)
    assert weights["D"] == 0.0
    assert weights.sum() == pytest.approx(0.60)


def test_missing_signal_inputs_produce_unavailable_status() -> None:
    result = construct_target_allocation(
        "equal_weight",
        SIGNAL_DATE,
        pd.Series({"AAA": np.nan}),
        pd.Series({"AAA": 10.0}),
        pd.Series({"AAA": True}),
        _config(top_n=1, max_weight=1.0),
    )

    assert result.status == "unavailable"
    assert result.cash_weight == 1.0
    assert result.reasons == ["no_complete_signal_inputs"]
