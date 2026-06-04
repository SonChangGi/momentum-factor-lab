import numpy as np
import pandas as pd

from momentum_factor_lab.factors import FACTOR_DEFINITIONS, compute_factor_scores


def fixture_prices():
    dates = pd.bdate_range("2020-01-01", periods=360)
    base = np.linspace(100, 160, len(dates))
    return pd.DataFrame({"AAA": base, "BBB": base[::-1] + 80}, index=dates)


def test_at_least_eight_factor_definitions():
    assert len(FACTOR_DEFINITIONS) >= 8


def test_factor_shapes_match_prices():
    prices = fixture_prices()
    factors = compute_factor_scores(prices)
    assert set(factors) == set(FACTOR_DEFINITIONS)
    for scores in factors.values():
        assert scores.shape == prices.shape
        assert scores.index.equals(prices.index)


def test_past_signal_does_not_change_when_future_price_changes():
    prices = fixture_prices()
    changed = prices.copy()
    signal_date = prices.index[250]
    changed.loc[prices.index[300]:, "AAA"] *= 10
    before = compute_factor_scores(prices)["mom_6_1"].loc[signal_date, "AAA"]
    after = compute_factor_scores(changed)["mom_6_1"].loc[signal_date, "AAA"]
    assert before == after
