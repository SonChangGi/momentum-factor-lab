from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _safe_div(numer: pd.DataFrame, denom: pd.DataFrame) -> pd.DataFrame:
    return numer.divide(denom.replace(0, np.nan))


def _weighted_sum(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    out = parts[0].copy()
    for part in parts[1:]:
        out = out.add(part, fill_value=np.nan)
    return out


def total_return_momentum(prices: pd.DataFrame, lookback: int, skip: int = 21) -> pd.DataFrame:
    return prices.shift(skip).divide(prices.shift(lookback + skip)) - 1.0


def simple_momentum(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    return prices.divide(prices.shift(lookback)) - 1.0


def multi_horizon_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return _weighted_sum(
        [
            0.15 * simple_momentum(prices, 21),
            0.25 * total_return_momentum(prices, 63, skip=5),
            0.30 * total_return_momentum(prices, 126, skip=10),
            0.30 * total_return_momentum(prices, 252, skip=21),
        ]
    )


def volatility_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    ret_126 = total_return_momentum(prices, 126, skip=10)
    vol = prices.pct_change().rolling(63).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(ret_126, vol)


def risk_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    mean = returns.rolling(126).mean() * TRADING_DAYS
    vol = returns.rolling(126).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(mean, vol)


def downside_risk_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    downside = returns.where(returns < 0, 0.0).rolling(126).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(total_return_momentum(prices, 126, skip=10), downside)


def dual_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    relative = total_return_momentum(prices, 126, skip=10)
    absolute = prices.divide(prices.rolling(200).mean()) - 1.0
    return relative.where(absolute > 0, relative - absolute.abs() - 1.0)


def moving_average_trend(prices: pd.DataFrame) -> pd.DataFrame:
    ma50 = prices.rolling(50).mean()
    ma200 = prices.rolling(200).mean()
    return prices.divide(ma200) - 1.0 + 0.5 * (ma50.divide(ma200) - 1.0)


def time_series_trend(prices: pd.DataFrame) -> pd.DataFrame:
    ma20 = prices.rolling(20).mean()
    ma100 = prices.rolling(100).mean()
    ma200 = prices.rolling(200).mean()
    return (prices > ma20).astype(float) + (ma20 > ma100).astype(float) + (ma100 > ma200).astype(float)


def drawdown_aware_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    ret_126 = total_return_momentum(prices, 126, skip=10)
    rolling_high = prices.rolling(126).max()
    drawdown = prices.divide(rolling_high) - 1.0
    return ret_126 + drawdown


def high_52week_proximity(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(252).max()) - 1.0


def breakout_63d(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(63).max()) - 1.0 + 0.5 * simple_momentum(prices, 21)


def reversal_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    long_mom = total_return_momentum(prices, 252, skip=21)
    short_reversal = simple_momentum(prices, 21)
    return long_mom - 0.35 * short_reversal


def acceleration_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    recent = simple_momentum(prices, 63)
    intermediate = total_return_momentum(prices, 126, skip=21)
    return recent - 0.5 * intermediate


def consistency_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    positive_ratio = returns.gt(0).rolling(126).mean()
    return total_return_momentum(prices, 126, skip=10) * positive_ratio


def low_vol_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    momentum = total_return_momentum(prices, 126, skip=10)
    vol = prices.pct_change().rolling(63).std() * np.sqrt(TRADING_DAYS)
    return momentum - vol


def relative_strength_6m(prices: pd.DataFrame) -> pd.DataFrame:
    momentum = total_return_momentum(prices, 126, skip=10)
    return momentum.rank(axis=1, pct=True)


def trend_quality(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    smoothness = returns.rolling(126).mean().divide(returns.rolling(126).std().replace(0, np.nan))
    trend = prices.divide(prices.rolling(126).mean()) - 1.0
    return trend + smoothness


def gap_resistant_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    clipped = returns.clip(lower=-0.08, upper=0.08)
    return (1.0 + clipped).rolling(126).apply(np.prod, raw=True) - 1.0


FactorFn = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True, slots=True)
class FactorSpec:
    name: str
    category: str
    formula: str
    description: str
    validation_notes: str
    fn: FactorFn


FACTOR_SPECS: dict[str, FactorSpec] = {
    spec.name: spec
    for spec in [
        FactorSpec("mom_12_1", "traditional", "P[t-21] / P[t-273] - 1", "Traditional 12-1 cross-sectional total return momentum.", "Manual shifted-return and no-lookahead tests.", lambda p: total_return_momentum(p, 252, skip=21)),
        FactorSpec("mom_9_1", "traditional", "P[t-21] / P[t-210] - 1", "Nine-month skipped return momentum.", "Manual shifted-return and no-lookahead tests.", lambda p: total_return_momentum(p, 189, skip=21)),
        FactorSpec("mom_6_1", "traditional", "P[t-21] / P[t-147] - 1", "Traditional 6-1 cross-sectional total return momentum.", "Manual shifted-return and no-lookahead tests.", lambda p: total_return_momentum(p, 126, skip=21)),
        FactorSpec("mom_3m", "recent", "P[t] / P[t-63] - 1", "Three-month recent momentum without skip month.", "Simple-return fixture tests.", lambda p: simple_momentum(p, 63)),
        FactorSpec("mom_1m", "recent", "P[t] / P[t-21] - 1", "One-month short-horizon momentum.", "Simple-return fixture tests.", lambda p: simple_momentum(p, 21)),
        FactorSpec("multi_horizon", "composite", "0.15*1m + 0.25*3m(skip5) + 0.30*6m(skip10) + 0.30*12m(skip21)", "Weighted 1/3/6/12-month multi-horizon momentum composite.", "Component helper tests plus output audit.", multi_horizon_momentum),
        FactorSpec("vol_adjusted", "risk_adjusted", "6m(skip10) / annualized_vol_63d", "Six-month momentum scaled by recent annualized volatility.", "Division-by-zero and finite coverage audit.", volatility_adjusted_momentum),
        FactorSpec("risk_adjusted", "risk_adjusted", "annualized_mean_return_126d / annualized_vol_126d", "Rolling Sharpe-like annualized return divided by volatility.", "Rolling mean/vol helper tests.", risk_adjusted_momentum),
        FactorSpec("downside_risk_adjusted", "risk_adjusted", "6m(skip10) / annualized_downside_vol_126d", "Momentum scaled by downside volatility only.", "Downside fixture tests and finite audit.", downside_risk_adjusted_momentum),
        FactorSpec("dual_momentum", "trend", "6m relative momentum penalized when price < MA200", "Relative momentum penalized when absolute trend is below the 200-day average.", "Trend penalty and no-lookahead audit.", dual_momentum),
        FactorSpec("ma_trend", "trend", "P/MA200 - 1 + 0.5*(MA50/MA200 - 1)", "Trend persistence from price/MA200 and MA50/MA200 structure.", "Moving-average fixture tests.", moving_average_trend),
        FactorSpec("time_series_trend", "trend", "I(P>MA20)+I(MA20>MA100)+I(MA100>MA200)", "Discrete time-series trend stack across short/intermediate/long averages.", "Bounded 0..3 output audit.", time_series_trend),
        FactorSpec("drawdown_aware", "drawdown", "6m(skip10) + P/rolling_high_126 - 1", "Six-month momentum penalized by recent drawdown from rolling high.", "Drawdown sign and no-lookahead audit.", drawdown_aware_momentum),
        FactorSpec("high_52w", "drawdown", "P / rolling_high_252 - 1", "Closeness to 52-week high; less negative is stronger.", "Manual rolling-high fixture tests.", high_52week_proximity),
        FactorSpec("breakout_63d", "breakout", "P/rolling_high_63 - 1 + 0.5*1m", "Recent breakout pressure with one-month confirmation.", "Rolling-high plus 1m fixture tests.", breakout_63d),
        FactorSpec("reversal_adjusted", "reversal", "12-1 momentum - 0.35*1m momentum", "12-1 momentum adjusted for short-term reversal risk.", "Component helper tests plus no-lookahead audit.", reversal_adjusted_momentum),
        FactorSpec("acceleration", "acceleration", "3m momentum - 0.5*6-1 momentum", "Momentum acceleration toward recent leadership.", "Manual acceleration fixture tests.", acceleration_momentum),
        FactorSpec("consistency", "quality", "6m(skip10) * rolling_positive_return_ratio_126d", "Rewards momentum earned consistently across days.", "Positive-ratio fixture tests.", consistency_momentum),
        FactorSpec("low_vol_momentum", "risk_adjusted", "6m(skip10) - annualized_vol_63d", "Momentum penalized by high recent volatility.", "Low-vol ranking fixture tests.", low_vol_momentum),
        FactorSpec("relative_strength_6m", "cross_sectional", "cross-sectional percentile_rank(6m(skip10))", "Six-month relative-strength percentile within the eligible universe.", "Cross-sectional rank audit.", relative_strength_6m),
        FactorSpec("trend_quality", "quality", "P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126", "Combines trend slope with smoothness of returns.", "Rolling helper and finite audit.", trend_quality),
        FactorSpec("gap_resistant", "robust", "compound clipped daily returns over 126d", "Momentum using clipped daily returns to reduce single-gap dominance.", "Clipped-return fixture tests.", gap_resistant_momentum),
    ]
}

FACTOR_DEFINITIONS: dict[str, FactorFn] = {name: spec.fn for name, spec in FACTOR_SPECS.items()}
FACTOR_DESCRIPTIONS: dict[str, str] = {name: spec.description for name, spec in FACTOR_SPECS.items()}


def compute_factor_scores(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {name: spec.fn(prices).replace([np.inf, -np.inf], np.nan) for name, spec in FACTOR_SPECS.items()}


def factor_definitions_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "factor": spec.name,
                "category": spec.category,
                "formula": spec.formula,
                "description": spec.description,
                "validation_notes": spec.validation_notes,
            }
            for spec in FACTOR_SPECS.values()
        ]
    )


def validate_factor_library(prices: pd.DataFrame, *, max_symbols: int = 50) -> pd.DataFrame:
    sample = prices.dropna(axis=1, how="all").iloc[:, :max_symbols]
    if sample.empty:
        return pd.DataFrame(
            [
                {
                    "factor": name,
                    "metadata_check": True,
                    "shape_check": False,
                    "finite_coverage": 0.0,
                    "no_lookahead_check": False,
                    "status": "fail",
                    "detail": "no price sample available",
                }
                for name in FACTOR_SPECS
            ]
        )
    base_scores = compute_factor_scores(sample)
    rows: list[dict[str, object]] = []
    signal_pos = min(max(260, len(sample.index) // 2), max(len(sample.index) - 2, 0))
    signal_date = sample.index[signal_pos]
    changed = sample.copy()
    if signal_pos + 1 < len(changed.index):
        changed.iloc[signal_pos + 1 :] = changed.iloc[signal_pos + 1 :] * 7.0
    changed_scores = compute_factor_scores(changed)
    for name, spec in FACTOR_SPECS.items():
        scores = base_scores[name]
        metadata_check = all([spec.name, spec.category, spec.formula, spec.description, spec.validation_notes])
        shape_check = scores.shape == sample.shape and scores.index.equals(sample.index) and list(scores.columns) == list(sample.columns)
        finite_coverage = float(np.isfinite(scores.to_numpy(dtype=float, copy=True)).mean()) if scores.size else 0.0
        before = scores.loc[signal_date]
        after = changed_scores[name].loc[signal_date]
        comparable = before.dropna().index.intersection(after.dropna().index)
        if len(comparable) == 0:
            no_lookahead = True
        else:
            no_lookahead = bool(np.allclose(before.loc[comparable], after.loc[comparable], equal_nan=True))
        status = "pass" if metadata_check and shape_check and finite_coverage > 0.01 and no_lookahead else "fail"
        rows.append(
            {
                "factor": name,
                "category": spec.category,
                "metadata_check": bool(metadata_check),
                "shape_check": bool(shape_check),
                "finite_coverage": finite_coverage,
                "no_lookahead_check": no_lookahead,
                "formula": spec.formula,
                "validation_notes": spec.validation_notes,
                "validation_sample_symbols": sample.shape[1],
                "validation_signal_date": str(signal_date.date()) if hasattr(signal_date, "date") else str(signal_date),
                "status": status,
            }
        )
    return pd.DataFrame(rows)
