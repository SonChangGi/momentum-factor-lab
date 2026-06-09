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


def _drift_weight_values(
    weight_values: np.ndarray,
    start_values: np.ndarray,
    end_values: np.ndarray,
) -> np.ndarray:
    weight_values = np.asarray(weight_values, dtype=float)
    start_values = np.asarray(start_values, dtype=float)
    end_values = np.asarray(end_values, dtype=float)
    held = weight_values != 0.0
    valid = held & np.isfinite(start_values) & np.isfinite(end_values) & (start_values > 0.0) & (end_values > 0.0)
    stale_held = held & ~valid
    drifted_values = np.zeros(len(weight_values), dtype=float)
    if not (bool(valid.any()) or bool(stale_held.any())):
        return drifted_values
    gross = weight_values[valid] * end_values[valid] / start_values[valid]
    stale_notional = np.clip(weight_values[stale_held], a_min=0.0, a_max=None)
    cash_weight = max(0.0, 1.0 - float(weight_values.sum()))
    total = float(gross.sum()) + float(stale_notional.sum()) + cash_weight
    if total <= 0 or not np.isfinite(total):
        return drifted_values
    if gross.size:
        drifted_values[valid] = gross / total
    if stale_notional.size:
        # Missing/nonpositive trade-date prices should not erase a held position
        # from turnover diagnostics. Carry the last target notional so an exit
        # still records sell turnover and cost rather than disappearing.
        drifted_values[stale_held] = stale_notional / total
    return drifted_values


def _drift_weight_matrix(
    weight_values: np.ndarray,
    start_values: np.ndarray,
    end_values: np.ndarray,
) -> np.ndarray:
    weight_values = np.asarray(weight_values, dtype=float)
    start_values = np.asarray(start_values, dtype=float)
    end_values = np.asarray(end_values, dtype=float)
    if end_values.ndim == 1:
        return _drift_weight_values(weight_values, start_values, end_values)[np.newaxis, :]

    drifted_values = np.zeros_like(end_values, dtype=float)
    if end_values.size == 0:
        return drifted_values
    held = weight_values != 0.0
    if not bool(held.any()):
        return drifted_values

    valid_start = np.isfinite(start_values) & (start_values > 0.0)
    valid_end = np.isfinite(end_values) & (end_values > 0.0)
    valid = valid_end & (held & valid_start)

    gross = np.zeros_like(end_values, dtype=float)
    denominator = np.where(valid_start, start_values, np.nan)
    np.divide(end_values, denominator, out=gross, where=valid)
    gross *= weight_values
    gross = np.where(valid, gross, 0.0)

    stale_held = (~valid) & held
    stale_notional = np.where(stale_held, np.clip(weight_values, a_min=0.0, a_max=None), 0.0)
    cash_weight = max(0.0, 1.0 - float(weight_values.sum()))
    totals = gross.sum(axis=1) + stale_notional.sum(axis=1) + cash_weight
    usable = np.isfinite(totals) & (totals > 0.0)
    if not bool(usable.any()):
        return drifted_values
    drifted_values[usable] = (gross[usable] + stale_notional[usable]) / totals[usable, np.newaxis]
    return drifted_values


def _drift_weights(
    weights: pd.Series,
    start_prices: pd.Series,
    end_prices: pd.Series,
) -> pd.Series:
    index = weights.index
    weight_values = pd.to_numeric(weights.reindex(index), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    start_values = pd.to_numeric(start_prices.reindex(index), errors="coerce").to_numpy(dtype=float)
    end_values = pd.to_numeric(end_prices.reindex(index), errors="coerce").to_numpy(dtype=float)
    drifted_values = _drift_weight_values(weight_values, start_values, end_values)
    return pd.Series(drifted_values, index=index, dtype=float)


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
    numeric_prices = prices.apply(pd.to_numeric, errors="coerce")
    price_values = numeric_prices.to_numpy(dtype=float)
    returns = prices.pct_change().fillna(0.0)
    costs = pd.Series(0.0, index=prices.index)
    turnover = pd.Series(0.0, index=prices.index)
    naive_turnover = pd.Series(0.0, index=prices.index)
    pre_trade_weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    signal_dates: dict[pd.Timestamp, pd.Timestamp] = {}
    trade_effective_targets: dict[pd.Timestamp, tuple[pd.Series, pd.Timestamp]] = {}
    last_target = pd.Series(0.0, index=prices.columns)
    last_target_values = np.zeros(len(prices.columns), dtype=float)
    last_trade_price_date: pd.Timestamp | None = None
    date_positions = {date: position for position, date in enumerate(prices.index)}

    rebalance_dates = _rebalance_dates(prices.index, config.rebalance_frequency)
    for rebalance_date in rebalance_dates:
        loc = date_positions[rebalance_date]
        if loc == 0:
            continue
        signal_date = prices.index[int(loc) - 1]
        scores = _eligible_scores_at(factor_scores.loc[signal_date], eligibility_mask, signal_date)
        target = balanced_weights(scores, top_n=config.top_n, max_weight=config.max_weight)
        target = target.reindex(prices.columns).fillna(0.0)
        target_values = target.to_numpy(dtype=float)
        if last_trade_price_date is None:
            drifted_pre_trade_values = np.zeros(len(prices.columns), dtype=float)
        else:
            drifted_pre_trade_values = _drift_weight_values(
                last_target_values,
                price_values[date_positions[last_trade_price_date]],
                price_values[date_positions[signal_date]],
            )
        trade_turnover = float(np.abs(target_values - drifted_pre_trade_values).sum())
        target_turnover = float((target - last_target).abs().sum())
        pre_trade_weights.loc[rebalance_date] = drifted_pre_trade_values
        turnover.loc[rebalance_date] = trade_turnover
        naive_turnover.loc[rebalance_date] = target_turnover
        # Apply transaction/slippage cost on the next trading day after the rebalance signal.
        if int(loc) + 1 < len(prices.index):
            effective_date = prices.index[int(loc) + 1]
            costs.loc[effective_date] += trade_turnover * config.total_cost_rate
            trade_effective_targets[effective_date] = (target, rebalance_date)
        signal_dates[rebalance_date] = signal_date
        last_target = target
        last_target_values = target_values
        last_trade_price_date = rebalance_date

    effective_weights_values = np.zeros((len(prices.index), len(prices.columns)), dtype=float)
    effective_events = sorted(trade_effective_targets.items(), key=lambda item: item[0])
    for event_index, (effective_date, (current_target, current_trade_price_date)) in enumerate(effective_events):
        start_pos = date_positions[effective_date]
        stop_pos = (
            date_positions[effective_events[event_index + 1][0]]
            if event_index + 1 < len(effective_events)
            else len(prices.index)
        )
        if start_pos >= stop_pos:
            continue
        prior_positions = np.arange(start_pos, stop_pos, dtype=int) - 1
        prior_positions = np.maximum(prior_positions, date_positions[current_trade_price_date])
        effective_weights_values[start_pos:stop_pos] = _drift_weight_matrix(
            current_target.to_numpy(dtype=float),
            price_values[date_positions[current_trade_price_date]],
            price_values[prior_positions],
        )
    effective_weights = pd.DataFrame(effective_weights_values, index=prices.index, columns=prices.columns)
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
