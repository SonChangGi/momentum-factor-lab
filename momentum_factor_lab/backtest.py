from __future__ import annotations

from dataclasses import dataclass, field

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
    pre_trade_weights: pd.DataFrame = field(default_factory=pd.DataFrame)
    naive_turnover: pd.Series = field(default_factory=pd.Series)


def _rebalance_dates(index: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    if index.empty:
        return index
    if frequency == "M":
        frequency = "ME"
    sampled = pd.Series(index=index, data=index).resample(frequency).last().dropna()
    dates = pd.DatetimeIndex(sampled.values)
    return dates.intersection(index)



def _drift_weights(
    weights: pd.Series,
    start_prices: pd.Series,
    end_prices: pd.Series,
) -> pd.Series:
    aligned = pd.concat(
        [weights.rename("weight"), start_prices.rename("start"), end_prices.rename("end")],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    held = aligned["weight"].fillna(0.0).ne(0.0)
    valid = held & aligned["start"].gt(0) & aligned["end"].gt(0)
    stale_held = held & ~valid
    drifted = pd.Series(0.0, index=weights.index, dtype=float)
    if not (valid.any() or stale_held.any()):
        return drifted
    gross = aligned.loc[valid, "weight"] * aligned.loc[valid, "end"] / aligned.loc[valid, "start"]
    stale_notional = aligned.loc[stale_held, "weight"].clip(lower=0.0)
    cash_weight = max(0.0, 1.0 - float(aligned["weight"].fillna(0.0).sum()))
    total = float(gross.sum()) + float(stale_notional.sum()) + cash_weight
    if total <= 0 or not np.isfinite(total):
        return drifted
    if not gross.empty:
        drifted.loc[gross.index] = gross / total
    if not stale_notional.empty:
        # Missing/nonpositive trade-date prices should not erase a held position
        # from turnover diagnostics. Carry the last target notional so an exit
        # still records sell turnover and cost rather than disappearing.
        drifted.loc[stale_notional.index] = stale_notional / total
    return drifted


def _eligible_scores_at(
    scores: pd.Series,
    eligibility_mask: pd.DataFrame | None,
    signal_date: pd.Timestamp,
) -> pd.Series:
    if eligibility_mask is None or eligibility_mask.empty:
        return scores
    if signal_date not in eligibility_mask.index:
        return scores.iloc[0:0]
    eligible = eligibility_mask.loc[signal_date].reindex(scores.index).fillna(False).astype(bool)
    return scores.where(eligible)

def run_factor_backtest(
    prices: pd.DataFrame,
    factor_scores: pd.DataFrame,
    config: RunConfig,
    factor_name: str,
    eligibility_mask: pd.DataFrame | None = None,
) -> BacktestResult:
    prices = prices.sort_index().dropna(how="all")
    factor_scores = factor_scores.reindex_like(prices)
    returns = prices.pct_change().fillna(0.0)
    # NaN means "no new rebalance instruction"; explicit zeros on rebalance rows mean "exit/sell".
    scheduled_weights = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    costs = pd.Series(0.0, index=prices.index)
    turnover = pd.Series(0.0, index=prices.index)
    naive_turnover = pd.Series(0.0, index=prices.index)
    pre_trade_weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    signal_dates: dict[pd.Timestamp, pd.Timestamp] = {}
    last_target = pd.Series(0.0, index=prices.columns)
    last_trade_price_date: pd.Timestamp | None = None

    rebalance_dates = _rebalance_dates(prices.index, config.rebalance_frequency)
    for rebalance_date in rebalance_dates:
        loc = prices.index.get_loc(rebalance_date)
        if isinstance(loc, slice):
            loc = loc.start
        if loc == 0:
            continue
        signal_date = prices.index[int(loc) - 1]
        scores = _eligible_scores_at(factor_scores.loc[signal_date], eligibility_mask, signal_date)
        target = balanced_weights(scores, top_n=config.top_n, max_weight=config.max_weight)
        target = target.reindex(prices.columns).fillna(0.0)
        if last_trade_price_date is None:
            drifted_pre_trade = pd.Series(0.0, index=prices.columns, dtype=float)
        else:
            drifted_pre_trade = _drift_weights(
                last_target,
                prices.loc[last_trade_price_date].reindex(prices.columns),
                prices.loc[signal_date].reindex(prices.columns),
            )
        trade_turnover = float((target - drifted_pre_trade).abs().sum())
        target_turnover = float((target - last_target).abs().sum())
        scheduled_weights.loc[rebalance_date] = target
        pre_trade_weights.loc[rebalance_date] = drifted_pre_trade
        turnover.loc[rebalance_date] = trade_turnover
        naive_turnover.loc[rebalance_date] = target_turnover
        # Apply transaction/slippage cost on the next trading day after the rebalance signal.
        if int(loc) + 1 < len(prices.index):
            costs.iloc[int(loc) + 1] += trade_turnover * config.total_cost_rate
        signal_dates[rebalance_date] = signal_date
        last_target = target
        last_trade_price_date = signal_date

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
        pre_trade_weights=pre_trade_weights,
        naive_turnover=naive_turnover[naive_turnover > 0].rename(factor_name),
    )
