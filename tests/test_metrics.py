import math

import pandas as pd

from momentum_factor_lab.metrics import calmar_ratio, max_drawdown, metric_summary, sharpe_ratio, sortino_ratio


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


def test_metric_summary_reports_turnover_and_cost_diagnostics():
    returns = pd.Series([0.01, -0.02, 0.03, 0.00])
    turnover = pd.Series([0.25, 0.75], index=[returns.index[1], returns.index[3]])
    costs = pd.Series([0.001, 0.002, 0.0, 0.003])

    summary = metric_summary(returns, turnover, costs)

    assert summary["avg_turnover"] == 0.5
    assert summary["total_turnover"] == 1.0
    assert summary["turnover_events"] == 2.0
    assert summary["annualized_turnover"] == 63.0
    assert math.isclose(summary["total_cost"], 0.006)
    assert math.isclose(summary["avg_daily_cost"], 0.0015)
    assert math.isclose(summary["annualized_cost_drag"], 0.378)
