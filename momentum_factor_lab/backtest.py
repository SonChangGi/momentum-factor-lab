from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import RunConfig
from .portfolio import balanced_weights


@dataclass(slots=True)
class BacktestResult:
    factor_name: str
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    signal_dates: pd.Series


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    if index.empty:
        return index
    if frequency == "M":
        frequency = "ME"
    sampled = pd.Series(index=index, data=index).resample(frequency).last().dropna()
    dates = pd.DatetimeIndex(sampled.values)
    return dates.intersection(index)


def run_factor_backtest(
    prices: pd.DataFrame,
    factor_scores: pd.DataFrame,
    config: RunConfig,
    factor_name: str,
) -> BacktestResult:
    prices = prices.sort_index().dropna(how="all")
    factor_scores = factor_scores.reindex_like(prices)
    returns = prices.pct_change().fillna(0.0)
    # NaN means "no new rebalance instruction"; explicit zeros on rebalance rows mean "exit/sell".
    scheduled_weights = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    costs = pd.Series(0.0, index=prices.index)
    turnover = pd.Series(0.0, index=prices.index)
    signal_dates: dict[pd.Timestamp, pd.Timestamp] = {}
    last_target = pd.Series(0.0, index=prices.columns)

    rebalance_dates = _rebalance_dates(prices.index, config.rebalance_frequency)
    for rebalance_date in rebalance_dates:
        loc = prices.index.get_loc(rebalance_date)
        if isinstance(loc, slice):
            loc = loc.start
        if loc == 0:
            continue
        signal_date = prices.index[int(loc) - 1]
        scores = factor_scores.loc[signal_date]
        target = balanced_weights(scores, top_n=config.top_n, max_weight=config.max_weight)
        target = target.reindex(prices.columns).fillna(0.0)
        trade_turnover = float((target - last_target).abs().sum())
        scheduled_weights.loc[rebalance_date] = target
        turnover.loc[rebalance_date] = trade_turnover
        # Apply transaction/slippage cost on the next trading day after the rebalance signal.
        if int(loc) + 1 < len(prices.index):
            costs.iloc[int(loc) + 1] += trade_turnover * config.total_cost_rate
        signal_dates[rebalance_date] = signal_date
        last_target = target

    scheduled_weights = scheduled_weights.ffill().fillna(0.0)
    # Conservative one-day execution delay: today's returns use yesterday's scheduled weights.
    effective_weights = scheduled_weights.shift(1).fillna(0.0)
    portfolio_returns = (effective_weights * returns).sum(axis=1) - costs
    equity = (1.0 + portfolio_returns).cumprod()
    return BacktestResult(
        factor_name=factor_name,
        returns=portfolio_returns.rename(factor_name),
        equity=equity.rename(factor_name),
        weights=effective_weights,
        turnover=turnover[turnover > 0].rename(factor_name),
        costs=costs.rename(factor_name),
        signal_dates=pd.Series(signal_dates, name="signal_date"),
    )
