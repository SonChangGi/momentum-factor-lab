import numpy as np
import pandas as pd

from momentum_factor_lab.backtest import run_factor_backtest
from momentum_factor_lab.config import RunConfig


def test_backtest_uses_one_day_execution_delay():
    dates = pd.bdate_range("2021-01-01", periods=90)
    prices = pd.DataFrame({"A": np.linspace(100, 140, len(dates)), "B": np.linspace(100, 80, len(dates))}, index=dates)
    scores = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates)
    config = RunConfig(start_date="2021-01-01", end_date="2021-05-01", top_n=1, max_weight=1.0)
    result = run_factor_backtest(prices, scores, config, "test")
    first_weight_day = result.weights.index[result.weights["A"].gt(0)][0]
    first_rebalance_day = result.signal_dates.index[0]
    assert first_weight_day > first_rebalance_day
    assert result.signal_dates.iloc[0] < first_rebalance_day


def test_costs_reduce_returns_on_turnover():
    dates = pd.bdate_range("2021-01-01", periods=90)
    prices = pd.DataFrame({"A": np.linspace(100, 130, len(dates)), "B": np.linspace(100, 120, len(dates))}, index=dates)
    scores = pd.DataFrame({"A": 1.0, "B": 0.5}, index=dates)
    no_cost = RunConfig(transaction_cost_bps=0, slippage_bps=0, top_n=1, max_weight=1.0)
    with_cost = RunConfig(transaction_cost_bps=50, slippage_bps=50, top_n=1, max_weight=1.0)
    a = run_factor_backtest(prices, scores, no_cost, "test").returns.sum()
    b = run_factor_backtest(prices, scores, with_cost, "test").returns.sum()
    assert b < a


def test_rebalance_to_zero_exits_prior_position_without_leverage():
    dates = pd.bdate_range("2021-01-01", periods=160)
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    scores = pd.DataFrame({"A": 1.0, "B": -1.0}, index=dates)
    scores.loc[dates[70]:, "A"] = -1.0
    scores.loc[dates[70]:, "B"] = 1.0
    config = RunConfig(start_date="2021-01-01", end_date="2021-08-31", top_n=1, max_weight=1.0)
    result = run_factor_backtest(prices, scores, config, "switch")
    assert result.weights.sum(axis=1).max() <= 1.0
    assert result.weights["A"].iloc[-1] == 0.0
    assert result.weights["B"].iloc[-1] == 1.0


def test_backtest_never_holds_more_than_top_20_names():
    dates = pd.bdate_range("2021-01-01", periods=180)
    symbols = [f"S{i:02d}" for i in range(30)]
    prices = pd.DataFrame({symbol: np.linspace(100, 130 + i, len(dates)) for i, symbol in enumerate(symbols)}, index=dates)
    scores = pd.DataFrame({symbol: 100 - i for i, symbol in enumerate(symbols)}, index=dates)
    config = RunConfig(start_date="2021-01-01", end_date="2021-09-30", top_n=20, max_weight=0.05)
    result = run_factor_backtest(prices, scores, config, "top20")
    assert result.weights.gt(0).sum(axis=1).max() <= 20


def test_turnover_cost_diagnostics_match_configured_cost_rate():
    dates = pd.bdate_range("2021-01-01", periods=90)
    prices = pd.DataFrame({"A": np.linspace(100, 130, len(dates)), "B": np.linspace(100, 120, len(dates))}, index=dates)
    scores = pd.DataFrame({"A": 1.0, "B": 0.5}, index=dates)
    config = RunConfig(transaction_cost_bps=25, slippage_bps=25, top_n=1, max_weight=1.0)

    result = run_factor_backtest(prices, scores, config, "cost_rate")

    assert result.turnover.sum() > 0
    assert np.isclose(result.costs.sum(), result.turnover.sum() * config.total_cost_rate)
