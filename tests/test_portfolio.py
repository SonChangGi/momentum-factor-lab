import numpy as np
import pandas as pd
import pytest

from momentum_factor_lab.portfolio import evidence_weighted_recommendation_table


def _base_recommendations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rank": [1, 2, 3, 4],
            "symbol": ["AAA", "BBB", "CCC", "DDD"],
            "score": [3.0, 2.0, 1.0, -0.5],
            "weight": [0.25, 0.25, 0.25, 0.25],
            "avg_dollar_volume_63d": [10_000_000, 80_000_000, 30_000_000, 5_000_000],
            "market_cap": [1_000_000_000, 12_000_000_000, np.nan, 500_000_000],
            "market_cap_source": ["provided", "provided", "unavailable", "provided"],
        }
    )


def test_evidence_weighted_recommendation_table_is_non_equal_and_capped():
    result = evidence_weighted_recommendation_table(_base_recommendations(), max_weight=0.40)

    assert result["weight"].gt(0).all()
    assert result["weight"].le(0.40 + 1e-12).all()
    assert result["weight"].sum() == pytest.approx(1.0)
    assert result["weight"].nunique() > 1
    assert result.loc[result["symbol"].eq("BBB"), "weight"].item() > result.loc[
        result["symbol"].eq("DDD"), "weight"
    ].item()
    assert result["weighting_method"].eq("score_size_liquidity").all()
    assert result["pre_cap_weight"].sum() == pytest.approx(1.0)


def test_evidence_weighting_falls_back_to_liquidity_proxy_without_market_cap():
    frame = _base_recommendations().drop(columns=["market_cap"])
    result = evidence_weighted_recommendation_table(frame, max_weight=0.50)

    assert result["market_cap"].isna().all()
    assert result["market_cap_source"].eq("unavailable").all()
    assert result["size_component_source"].eq("liquidity_proxy_63d_adv").all()
    assert result["liquidity_component"].gt(0).all()
    assert result["weight"].sum() == pytest.approx(1.0)


def test_evidence_weighting_reports_cash_when_cap_prevents_full_allocation():
    result = evidence_weighted_recommendation_table(_base_recommendations(), max_weight=0.20)

    assert result["weight"].le(0.20 + 1e-12).all()
    assert result["weight"].sum() == pytest.approx(0.80)
    assert result["weight_cap_excess"].ge(0).all()


def test_evidence_weighting_rejects_invalid_component_weights():
    with pytest.raises(ValueError, match="non-negative"):
        evidence_weighted_recommendation_table(_base_recommendations(), max_weight=0.40, score_weight=-0.1)
    with pytest.raises(ValueError, match="at least one"):
        evidence_weighted_recommendation_table(
            _base_recommendations(),
            max_weight=0.40,
            score_weight=0,
            market_cap_weight=0,
            liquidity_weight=0,
        )
    with pytest.raises(ValueError, match="rank_floor"):
        evidence_weighted_recommendation_table(_base_recommendations(), max_weight=0.40, rank_floor=-0.01)
