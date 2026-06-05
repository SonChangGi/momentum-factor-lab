import numpy as np
import pandas as pd

from momentum_factor_lab.factors import (
    FACTOR_DEFINITIONS,
    FACTOR_SPECS,
    acceleration_momentum,
    compute_factor_scores,
    consistency_momentum,
    high_52week_proximity,
    simple_momentum,
    total_return_momentum,
    validate_factor_library,
)


def fixture_prices(columns=2, periods=360):
    dates = pd.bdate_range("2020-01-01", periods=periods)
    data = {}
    for i in range(columns):
        base = np.linspace(100 + i, 160 + i, len(dates))
        data[f"S{i:04d}"] = base if i % 2 == 0 else base[::-1] + 80
    return pd.DataFrame(data, index=dates)


def test_at_least_eighteen_factor_definitions_with_metadata():
    assert len(FACTOR_DEFINITIONS) >= 18
    assert set(FACTOR_DEFINITIONS) == set(FACTOR_SPECS)
    for spec in FACTOR_SPECS.values():
        assert spec.formula and spec.description and spec.category and spec.validation_notes


def test_factor_shapes_match_prices():
    prices = fixture_prices()
    factors = compute_factor_scores(prices)
    assert set(factors) == set(FACTOR_DEFINITIONS)
    for scores in factors.values():
        assert scores.shape == prices.shape
        assert scores.index.equals(prices.index)


def test_all_factors_past_signal_does_not_change_when_future_price_changes():
    prices = fixture_prices(columns=4)
    changed = prices.copy()
    signal_date = prices.index[280]
    changed.loc[prices.index[300]:, "S0000"] *= 10
    for name in FACTOR_DEFINITIONS:
        before = compute_factor_scores(prices)[name].loc[signal_date]
        after = compute_factor_scores(changed)[name].loc[signal_date]
        comparable = before.dropna().index.intersection(after.dropna().index)
        assert np.allclose(before.loc[comparable], after.loc[comparable], equal_nan=True), name


def test_core_formula_manual_checks():
    dates = pd.bdate_range("2020-01-01", periods=300)
    prices = pd.DataFrame({"AAA": np.arange(1, 301, dtype=float)}, index=dates)
    assert total_return_momentum(prices, 10, skip=2).iloc[20, 0] == prices.iloc[18, 0] / prices.iloc[8, 0] - 1
    assert simple_momentum(prices, 10).iloc[20, 0] == prices.iloc[20, 0] / prices.iloc[10, 0] - 1
    assert high_52week_proximity(prices).iloc[-1, 0] == 0.0
    expected_accel = simple_momentum(prices, 63) - 0.5 * total_return_momentum(prices, 126, skip=21)
    pd.testing.assert_frame_equal(acceleration_momentum(prices), expected_accel)
    assert consistency_momentum(prices).iloc[-1, 0] > 0


def test_factor_validation_audit_passes_fixture():
    audit = validate_factor_library(fixture_prices(columns=8, periods=380))
    assert len(audit) == len(FACTOR_DEFINITIONS)
    assert audit["status"].eq("pass").all()
    assert audit["no_lookahead_check"].all()


def test_every_factor_matches_independent_formula_construction():
    prices = fixture_prices(columns=5, periods=380)
    returns = prices.pct_change()
    mom_12_1 = total_return_momentum(prices, 252, skip=21)
    mom_9_1 = total_return_momentum(prices, 189, skip=21)
    mom_6_1 = total_return_momentum(prices, 126, skip=21)
    mom_3m = simple_momentum(prices, 63)
    mom_1m = simple_momentum(prices, 21)
    vol63 = returns.rolling(63).std() * np.sqrt(252)
    mean126 = returns.rolling(126).mean() * 252
    vol126 = returns.rolling(126).std() * np.sqrt(252)
    downside = returns.where(returns < 0, 0.0).rolling(126).std() * np.sqrt(252)
    ma20 = prices.rolling(20).mean()
    ma50 = prices.rolling(50).mean()
    ma100 = prices.rolling(100).mean()
    ma126 = prices.rolling(126).mean()
    ma200 = prices.rolling(200).mean()
    rolling_high63 = prices.rolling(63).max()
    rolling_high126 = prices.rolling(126).max()
    rolling_high252 = prices.rolling(252).max()
    clipped = returns.clip(lower=-0.08, upper=0.08)
    expected = {
        "mom_12_1": mom_12_1,
        "mom_9_1": mom_9_1,
        "mom_6_1": mom_6_1,
        "mom_3m": mom_3m,
        "mom_1m": mom_1m,
        "multi_horizon": 0.15 * mom_1m
        + 0.25 * total_return_momentum(prices, 63, skip=5)
        + 0.30 * total_return_momentum(prices, 126, skip=10)
        + 0.30 * total_return_momentum(prices, 252, skip=21),
        "vol_adjusted": total_return_momentum(prices, 126, skip=10).divide(vol63.replace(0, np.nan)),
        "risk_adjusted": mean126.divide(vol126.replace(0, np.nan)),
        "downside_risk_adjusted": total_return_momentum(prices, 126, skip=10).divide(
            downside.replace(0, np.nan)
        ),
        "dual_momentum": total_return_momentum(prices, 126, skip=10).where(
            prices.divide(ma200) - 1.0 > 0,
            total_return_momentum(prices, 126, skip=10) - (prices.divide(ma200) - 1.0).abs() - 1.0,
        ),
        "ma_trend": prices.divide(ma200) - 1.0 + 0.5 * (ma50.divide(ma200) - 1.0),
        "time_series_trend": (prices > ma20).astype(float)
        + (ma20 > ma100).astype(float)
        + (ma100 > ma200).astype(float),
        "drawdown_aware": total_return_momentum(prices, 126, skip=10)
        + prices.divide(rolling_high126)
        - 1.0,
        "high_52w": prices.divide(rolling_high252) - 1.0,
        "breakout_63d": prices.divide(rolling_high63) - 1.0 + 0.5 * mom_1m,
        "reversal_adjusted": mom_12_1 - 0.35 * mom_1m,
        "acceleration": mom_3m - 0.5 * mom_6_1,
        "consistency": total_return_momentum(prices, 126, skip=10) * returns.gt(0).rolling(126).mean(),
        "low_vol_momentum": total_return_momentum(prices, 126, skip=10) - vol63,
        "relative_strength_6m": total_return_momentum(prices, 126, skip=10).rank(axis=1, pct=True),
        "trend_quality": prices.divide(ma126) - 1.0
        + returns.rolling(126).mean().divide(returns.rolling(126).std().replace(0, np.nan)),
        "gap_resistant": (1.0 + clipped).rolling(126).apply(np.prod, raw=True) - 1.0,
    }
    scores = compute_factor_scores(prices)
    assert set(expected) == set(scores)
    for name, expected_scores in expected.items():
        pd.testing.assert_frame_equal(scores[name], expected_scores.replace([np.inf, -np.inf], np.nan), check_names=False)
