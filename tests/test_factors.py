import numpy as np
import pandas as pd

from momentum_factor_lab.factors import (
    FACTOR_DEFINITIONS,
    FACTOR_SPECS,
    acceleration_momentum,
    breakout_126d,
    compute_factor_scores,
    consistency_momentum,
    decay_adjusted_momentum,
    deep_skip_twelve_month_momentum,
    high_52week_proximity,
    high_26week_proximity,
    price_efficiency_momentum,
    range_position_momentum,
    range_position_252d_momentum,
    short_acceleration_momentum,
    simple_momentum,
    skipped_two_month_momentum,
    stability_adjusted_momentum,
    total_return_momentum,
    two_month_momentum,
    unskipped_six_month_momentum,
    validate_factor_library,
    winsorized_skip_momentum,
)


def fixture_prices(columns=2, periods=360):
    dates = pd.bdate_range("2020-01-01", periods=periods)
    data = {}
    for i in range(columns):
        base = np.linspace(100 + i, 160 + i, len(dates))
        data[f"S{i:04d}"] = base if i % 2 == 0 else base[::-1] + 80
    return pd.DataFrame(data, index=dates)


def test_at_least_thirty_five_factor_definitions_with_metadata():
    assert len(FACTOR_DEFINITIONS) >= 55
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


def test_expanded_price_only_factor_formula_checks():
    dates = pd.bdate_range("2020-01-01", periods=320)
    prices = pd.DataFrame(
        {
            "SMOOTH": np.linspace(100.0, 180.0, len(dates)),
            "CHOPPY": 140.0 + np.sin(np.arange(len(dates)) / 3.0) * 8.0,
        },
        index=dates,
    )
    returns = prices.pct_change()
    path_length = returns.abs().rolling(126).sum()
    direct_move = (prices.divide(prices.shift(126)) - 1.0).abs()
    skipped_6m = prices.shift(10).divide(prices.shift(136)) - 1.0
    expected_efficiency = skipped_6m * direct_move.divide(path_length.replace(0, np.nan))
    rolling_low = prices.rolling(126).min()
    rolling_high = prices.rolling(126).max()
    expected_range = skipped_6m + (prices - rolling_low).divide(
        (rolling_high - rolling_low).replace(0, np.nan)
    ) - 0.5

    pd.testing.assert_frame_equal(
        price_efficiency_momentum(prices),
        expected_efficiency,
        check_names=False,
    )
    pd.testing.assert_frame_equal(
        range_position_momentum(prices),
        expected_range,
        check_names=False,
    )
    assert price_efficiency_momentum(prices).iloc[-1]["SMOOTH"] > price_efficiency_momentum(
        prices
    ).iloc[-1]["CHOPPY"]


def test_stage2_price_only_factor_formula_checks():
    dates = pd.bdate_range("2020-01-01", periods=380)
    trend = np.linspace(100.0, 220.0, len(dates))
    seasonal = 150.0 + np.sin(np.arange(len(dates)) / 5.0) * 12.0 + np.linspace(
        0.0, 40.0, len(dates)
    )
    prices = pd.DataFrame({"TREND": trend, "SEASONAL": seasonal}, index=dates)
    returns = prices.pct_change()
    skipped_12_2 = prices.shift(42).divide(prices.shift(294)) - 1.0
    unskipped_6m = prices.divide(prices.shift(126)) - 1.0
    mom_2m = prices.divide(prices.shift(42)) - 1.0
    skipped_2_1 = prices.shift(21).divide(prices.shift(63)) - 1.0
    mom_1m = prices.divide(prices.shift(21)) - 1.0
    mom_3m = prices.divide(prices.shift(63)) - 1.0
    skipped_6m = prices.shift(10).divide(prices.shift(136)) - 1.0
    skipped_12_1 = prices.shift(21).divide(prices.shift(273)) - 1.0
    rolling_high126 = prices.rolling(126).max()
    rolling_high252 = prices.rolling(252).max()
    rolling_low252 = prices.rolling(252).min()
    vol126 = returns.rolling(126).std() * np.sqrt(252)
    winsorized = returns.shift(10).clip(lower=-0.05, upper=0.05)

    expected = {
        "mom_12_2": skipped_12_2,
        "mom_6m_unskipped": unskipped_6m,
        "mom_2m": mom_2m,
        "mom_2_1": skipped_2_1,
        "high_26w": prices.divide(rolling_high126) - 1.0,
        "breakout_126d": prices.divide(rolling_high126) - 1.0 + 0.5 * mom_3m,
        "short_acceleration": mom_1m - 0.5 * mom_3m,
        "decay_adjusted": skipped_6m - 0.25 * mom_1m.abs(),
        "stability_adjusted": skipped_6m.divide((1.0 + vol126).replace(0, np.nan)),
        "winsorized_skip": (1.0 + winsorized).rolling(126).apply(np.prod, raw=True) - 1.0,
        "range_position_252d": skipped_12_1
        + (prices - rolling_low252).divide((rolling_high252 - rolling_low252).replace(0, np.nan))
        - 0.5,
    }
    actual = {
        "mom_12_2": deep_skip_twelve_month_momentum(prices),
        "mom_6m_unskipped": unskipped_six_month_momentum(prices),
        "mom_2m": two_month_momentum(prices),
        "mom_2_1": skipped_two_month_momentum(prices),
        "high_26w": high_26week_proximity(prices),
        "breakout_126d": breakout_126d(prices),
        "short_acceleration": short_acceleration_momentum(prices),
        "decay_adjusted": decay_adjusted_momentum(prices),
        "stability_adjusted": stability_adjusted_momentum(prices),
        "winsorized_skip": winsorized_skip_momentum(prices),
        "range_position_252d": range_position_252d_momentum(prices),
    }

    assert expected.keys() <= FACTOR_DEFINITIONS.keys()
    for name, expected_scores in expected.items():
        pd.testing.assert_frame_equal(actual[name], expected_scores, check_names=False)


def test_expanded_price_only_factors_handle_flat_prices_without_inf():
    dates = pd.bdate_range("2020-01-01", periods=320)
    prices = pd.DataFrame({"FLAT": np.full(len(dates), 100.0)}, index=dates)

    efficiency = price_efficiency_momentum(prices)
    range_position = range_position_momentum(prices)
    scores = compute_factor_scores(prices)

    assert not np.isinf(efficiency.to_numpy(dtype=float)).any()
    assert not np.isinf(range_position.to_numpy(dtype=float)).any()
    assert not np.isinf(scores["price_efficiency"].to_numpy(dtype=float)).any()
    assert not np.isinf(scores["range_position"].to_numpy(dtype=float)).any()
    assert efficiency.dropna(how="all").empty
    assert range_position.dropna(how="all").empty


def test_factor_validation_audit_passes_fixture():
    audit = validate_factor_library(fixture_prices(columns=8, periods=380))
    assert len(audit) == len(FACTOR_DEFINITIONS)
    assert audit["status"].eq("pass").all()
    assert audit["no_lookahead_check"].all()


def test_every_factor_matches_independent_formula_construction():
    prices = fixture_prices(columns=5, periods=380)
    returns = prices.pct_change()
    mom_12_1 = total_return_momentum(prices, 252, skip=21)
    mom_12_2 = prices.shift(42).divide(prices.shift(294)) - 1.0
    mom_9_1 = total_return_momentum(prices, 189, skip=21)
    mom_6_1 = total_return_momentum(prices, 126, skip=21)
    mom_3_1 = prices.shift(21).divide(prices.shift(84)) - 1.0
    mom_10d = prices.divide(prices.shift(10)) - 1.0
    mom_6m_unskipped = prices.divide(prices.shift(126)) - 1.0
    mom_3m = simple_momentum(prices, 63)
    mom_2m = prices.divide(prices.shift(42)) - 1.0
    mom_2_1 = prices.shift(21).divide(prices.shift(63)) - 1.0
    mom_6m = prices.divide(prices.shift(126)) - 1.0
    mom_12m = prices.divide(prices.shift(252)) - 1.0
    mom_1m = simple_momentum(prices, 21)
    mom_6m_skip10 = prices.shift(10).divide(prices.shift(136)) - 1.0
    vol63 = returns.rolling(63).std() * np.sqrt(252)
    mean126 = returns.rolling(126).mean() * 252
    vol126 = returns.rolling(126).std() * np.sqrt(252)
    downside = returns.where(returns < 0, 0.0).rolling(126).std() * np.sqrt(252)
    ma20 = prices.rolling(20).mean()
    ma50 = prices.rolling(50).mean()
    ma100 = prices.rolling(100).mean()
    ma126 = prices.rolling(126).mean()
    ma200 = prices.rolling(200).mean()
    rolling_high20 = prices.rolling(20).max()
    rolling_high63 = prices.rolling(63).max()
    rolling_low126 = prices.rolling(126).min()
    rolling_high126 = prices.rolling(126).max()
    rolling_low252 = prices.rolling(252).min()
    rolling_high252 = prices.rolling(252).max()
    clipped = returns.clip(lower=-0.08, upper=0.08)
    winsorized = returns.shift(10).clip(lower=-0.05, upper=0.05)
    path_length = returns.abs().rolling(126).sum()
    direct_move = simple_momentum(prices, 126).abs()
    ulcer_drawdown = prices.divide(rolling_high126) - 1.0
    ulcer = ulcer_drawdown.pow(2).rolling(126).mean().pow(0.5)
    expected = {
        "mom_12_1": mom_12_1,
        "mom_9_1": mom_9_1,
        "mom_6_1": mom_6_1,
        "mom_12_2": mom_12_2,
        "mom_3_1": mom_3_1,
        "mom_10d": mom_10d,
        "mom_6m_unskipped": mom_6m_unskipped,
        "mom_3m": mom_3m,
        "mom_2m": mom_2m,
        "mom_2_1": mom_2_1,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
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
        "high_26w": prices.divide(rolling_high126) - 1.0,
        "breakout_63d": prices.divide(rolling_high63) - 1.0 + 0.5 * mom_1m,
        "breakout_126d": prices.divide(rolling_high126) - 1.0 + 0.5 * mom_3m,
        "reversal_adjusted": mom_12_1 - 0.35 * mom_1m,
        "acceleration": mom_3m - 0.5 * mom_6_1,
        "short_acceleration": mom_1m - 0.5 * mom_3m,
        "decay_adjusted": mom_6m_skip10 - 0.25 * mom_1m.abs(),
        "consistency": total_return_momentum(prices, 126, skip=10) * returns.gt(0).rolling(126).mean(),
        "low_vol_momentum": total_return_momentum(prices, 126, skip=10) - vol63,
        "stability_adjusted": mom_6m_skip10.divide((1.0 + vol126).replace(0, np.nan)),
        "relative_strength_6m": total_return_momentum(prices, 126, skip=10).rank(axis=1, pct=True),
        "trend_quality": prices.divide(ma126) - 1.0
        + returns.rolling(126).mean().divide(returns.rolling(126).std().replace(0, np.nan)),
        "gap_resistant": (1.0 + clipped).rolling(126).apply(np.prod, raw=True) - 1.0,
        "winsorized_skip": (1.0 + winsorized).rolling(126).apply(np.prod, raw=True) - 1.0,
        "price_efficiency": total_return_momentum(prices, 126, skip=10)
        * direct_move.divide(path_length.replace(0, np.nan)),
        "range_position": total_return_momentum(prices, 126, skip=10)
        + (prices - rolling_low126).divide((rolling_high126 - rolling_low126).replace(0, np.nan))
        - 0.5,
        "range_position_252d": mom_12_1
        + (prices - rolling_low252).divide((rolling_high252 - rolling_low252).replace(0, np.nan))
        - 0.5,
        "median_return_3m": returns.rolling(63).median() * 63,
        "median_return_6m": returns.rolling(126).median() * 126,
        "winsorized_3m": (1.0 + clipped).rolling(63).apply(np.prod, raw=True) - 1.0,
        "winsorized_12m": (1.0 + clipped).rolling(252).apply(np.prod, raw=True) - 1.0,
        "vol_adjusted_3m": mom_3m.divide(vol63.replace(0, np.nan)),
        "vol_adjusted_12m": mom_12_1.divide((returns.rolling(126).std() * np.sqrt(252)).replace(0, np.nan)),
        "downside_adjusted_12m": mom_12_1.divide((returns.where(returns < 0, 0.0).rolling(252).std() * np.sqrt(252)).replace(0, np.nan)),
        "ma_slope_50": ma50.divide(ma50.shift(21)) - 1.0,
        "price_vs_ma200": prices.divide(ma200) - 1.0,
        "ma_stack_quality": (prices > ma20).astype(float)
        + (ma20 > ma50).astype(float)
        + (ma50 > ma100).astype(float)
        + (ma100 > ma200).astype(float),
        "breakout_20d": prices.divide(rolling_high20) - 1.0 + 0.5 * mom_10d,
        "accel_1m_vs_3m": mom_1m - mom_3m,
        "accel_3m_vs_6m": mom_3m - mom_6m,
        "accel_6m_vs_12m": mom_6m - mom_12m,
        "ulcer_adjusted": total_return_momentum(prices, 126, skip=10).divide(ulcer.replace(0, np.nan)),
        "smooth_return_6m": mom_6m - returns.rolling(126).std(),
    }
    scores = compute_factor_scores(prices)
    assert set(expected).issubset(scores)
    for name, expected_scores in expected.items():
        pd.testing.assert_frame_equal(scores[name], expected_scores.replace([np.inf, -np.inf], np.nan), check_names=False)


def test_new_factor_golden_vectors_and_edge_cases():
    dates = pd.bdate_range("2024-01-01", periods=90)
    prices = pd.DataFrame({"AAA": np.arange(1, 91, dtype=float), "CONST": 10.0}, index=dates)
    scores = compute_factor_scores(prices)

    assert scores["mom_3_1"].iloc[84, 0] == prices.iloc[63, 0] / prices.iloc[0, 0] - 1.0
    assert scores["mom_10d"].iloc[20, 0] == prices.iloc[20, 0] / prices.iloc[10, 0] - 1.0
    assert scores["mom_2m"].iloc[50, 0] == prices.iloc[50, 0] / prices.iloc[8, 0] - 1.0
    assert scores["median_return_3m"].iloc[-1, 0] > 0
    assert scores["breakout_20d"].iloc[-1, 0] == 0.5 * scores["mom_10d"].iloc[-1, 0]
    assert scores["accel_1m_vs_3m"].iloc[-1, 0] == scores["mom_1m"].iloc[-1, 0] - scores["mom_3m"].iloc[-1, 0]
    assert np.isfinite(scores["ma_stack_quality"].dropna().to_numpy()).all()
    assert scores["winsorized_3m"].shape == prices.shape
    assert scores["vol_adjusted_3m"]["CONST"].dropna().empty
