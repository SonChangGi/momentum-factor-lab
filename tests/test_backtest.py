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


def test_backtest_applies_eligibility_mask_at_signal_date_before_selection():
    dates = pd.bdate_range("2021-01-01", periods=90)
    prices = pd.DataFrame({"A": np.linspace(100, 140, len(dates)), "B": np.linspace(100, 120, len(dates))}, index=dates)
    scores = pd.DataFrame({"A": 10.0, "B": 1.0}, index=dates)
    eligibility = pd.DataFrame(True, index=dates, columns=prices.columns)
    first_rebalance = pd.Series(index=dates, data=dates).resample("ME").last().dropna().iloc[0]
    first_signal = dates[dates.get_loc(first_rebalance) - 1]
    eligibility.loc[first_signal, "A"] = False
    config = RunConfig(start_date="2021-01-01", end_date="2021-05-01", top_n=1, max_weight=1.0)

    result = run_factor_backtest(prices, scores, config, "eligible", eligibility)

    first_weight_day = result.weights.index[result.weights.sum(axis=1).gt(0)][0]
    assert result.weights.loc[first_weight_day, "A"] == 0.0
    assert result.weights.loc[first_weight_day, "B"] == 1.0


def test_drifted_turnover_differs_from_naive_target_turnover_when_prices_move():
    dates = pd.bdate_range("2021-01-01", periods=160)
    prices = pd.DataFrame(
        {
            "A": np.r_[np.linspace(100, 120, 80), np.linspace(120, 240, 80)],
            "B": np.r_[np.linspace(100, 110, 80), np.linspace(110, 90, 80)],
        },
        index=dates,
    )
    scores = pd.DataFrame({"A": 1.0, "B": 0.9}, index=dates)
    config = RunConfig(start_date="2021-01-01", end_date="2021-08-31", top_n=2, max_weight=0.5)

    result = run_factor_backtest(prices, scores, config, "drift")

    assert result.turnover.sum() != result.naive_turnover.sum()
    assert not result.pre_trade_weights.empty


def test_backtest_weights_and_turnover_use_same_drifted_holdings_state():
    dates = pd.bdate_range("2021-01-01", periods=100)
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    rebalance_dates = pd.Series(index=dates, data=dates).resample("ME").last().dropna()
    first_rebalance = rebalance_dates.iloc[0]
    second_rebalance = rebalance_dates.iloc[1]
    start = dates.get_loc(first_rebalance)
    end = dates.get_loc(second_rebalance)
    prices.iloc[start : end + 1, prices.columns.get_loc("A")] = np.linspace(100.0, 200.0, end - start + 1)
    scores = pd.DataFrame({"A": 1.0, "B": 0.9}, index=dates)
    config = RunConfig(start_date="2021-01-01", end_date="2021-05-31", top_n=2, max_weight=0.5)

    result = run_factor_backtest(prices, scores, config, "drift_state")
    second_rebalance = result.signal_dates.index[1]
    pre_trade = result.pre_trade_weights.loc[second_rebalance]
    weights_before_second_rebalance_return = result.weights.loc[second_rebalance]

    assert pre_trade["A"] > 0.5
    assert pre_trade["B"] < 0.5
    assert np.isclose(pre_trade.sum(), 1.0)
    assert weights_before_second_rebalance_return["A"] > 0.5
    assert weights_before_second_rebalance_return["B"] < 0.5
    expected_turnover = abs(0.5 - pre_trade["A"]) + abs(0.5 - pre_trade["B"])
    assert np.isclose(result.turnover.loc[second_rebalance], expected_turnover)
    naive_second = result.naive_turnover.reindex([second_rebalance]).fillna(0.0).iloc[0]
    assert np.isclose(naive_second, 0.0)


def test_missing_trade_price_preserves_liquidation_turnover():
    dates = pd.bdate_range("2021-01-01", periods=90)
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    scores = pd.DataFrame({"A": 1.0, "B": 0.5}, index=dates)
    config = RunConfig(start_date="2021-01-01", end_date="2021-05-31", top_n=1, max_weight=1.0)
    rebalance_dates = pd.Series(index=dates, data=dates).resample("ME").last().dropna()
    second_rebalance = rebalance_dates.iloc[1]
    second_signal = dates[dates.get_loc(second_rebalance) - 1]
    scores.loc[second_signal:, ["A", "B"]] = [-1.0, 1.0]
    prices.loc[second_signal, "A"] = np.nan
    eligibility = pd.DataFrame(True, index=dates, columns=prices.columns)
    eligibility.loc[second_signal, "A"] = False

    result = run_factor_backtest(prices, scores, config, "missing_exit_price", eligibility)

    assert result.turnover.loc[second_rebalance] >= 1.99
    assert np.isclose(result.costs.sum(), result.turnover.sum() * config.total_cost_rate)
