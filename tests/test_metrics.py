import math

import pandas as pd

from momentum_factor_lab.metrics import calmar_ratio, max_drawdown, sharpe_ratio, sortino_ratio


def test_max_drawdown_known_path():
    returns = pd.Series([0.10, -0.10, -0.20, 0.05])
    assert round(max_drawdown(returns), 4) == -0.28


def test_ratios_handle_flat_returns():
    flat = pd.Series([0.0] * 20)
    assert sharpe_ratio(flat) == 0.0
    assert sortino_ratio(flat) == 0.0
    assert calmar_ratio(flat) == 0.0


def test_sortino_positive_no_downside_is_infinite():
    positive = pd.Series([0.001] * 20)
    assert math.isinf(sortino_ratio(positive))


def test_max_drawdown_counts_first_period_loss():
    assert round(max_drawdown(pd.Series([-0.10])), 8) == -0.10
