from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _safe_div(numer: pd.DataFrame, denom: pd.DataFrame) -> pd.DataFrame:
    return numer.divide(denom.replace(0, np.nan))


def total_return_momentum(prices: pd.DataFrame, lookback: int, skip: int = 21) -> pd.DataFrame:
    return prices.shift(skip).divide(prices.shift(lookback + skip)) - 1.0


def simple_momentum(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    return prices.divide(prices.shift(lookback)) - 1.0


def multi_horizon_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    parts = [
        0.15 * simple_momentum(prices, 21),
        0.25 * total_return_momentum(prices, 63, skip=5),
        0.30 * total_return_momentum(prices, 126, skip=10),
        0.30 * total_return_momentum(prices, 252, skip=21),
    ]
    return sum(parts)


def volatility_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    ret_126 = total_return_momentum(prices, 126, skip=10)
    vol = prices.pct_change().rolling(63).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(ret_126, vol)


def risk_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    mean = returns.rolling(126).mean() * TRADING_DAYS
    vol = returns.rolling(126).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(mean, vol)


def dual_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    relative = total_return_momentum(prices, 126, skip=10)
    absolute = prices.divide(prices.rolling(200).mean()) - 1.0
    return relative.where(absolute > 0, relative - absolute.abs() - 1.0)


def moving_average_trend(prices: pd.DataFrame) -> pd.DataFrame:
    ma50 = prices.rolling(50).mean()
    ma200 = prices.rolling(200).mean()
    return prices.divide(ma200) - 1.0 + 0.5 * (ma50.divide(ma200) - 1.0)


def drawdown_aware_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    ret_126 = total_return_momentum(prices, 126, skip=10)
    rolling_high = prices.rolling(126).max()
    drawdown = prices.divide(rolling_high) - 1.0
    return ret_126 + drawdown  # drawdown is <= 0, penalizing fragile momentum.


def reversal_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    long_mom = total_return_momentum(prices, 252, skip=21)
    short_reversal = simple_momentum(prices, 21)
    return long_mom - 0.35 * short_reversal


FactorFn = Callable[[pd.DataFrame], pd.DataFrame]

FACTOR_DEFINITIONS: dict[str, FactorFn] = {
    "mom_12_1": lambda p: total_return_momentum(p, 252, skip=21),
    "mom_6_1": lambda p: total_return_momentum(p, 126, skip=21),
    "mom_3m": lambda p: simple_momentum(p, 63),
    "multi_horizon": multi_horizon_momentum,
    "vol_adjusted": volatility_adjusted_momentum,
    "risk_adjusted": risk_adjusted_momentum,
    "dual_momentum": dual_momentum,
    "ma_trend": moving_average_trend,
    "drawdown_aware": drawdown_aware_momentum,
    "reversal_adjusted": reversal_adjusted_momentum,
}

FACTOR_DESCRIPTIONS: dict[str, str] = {
    "mom_12_1": "Traditional 12-1 cross-sectional total return momentum.",
    "mom_6_1": "Traditional 6-1 cross-sectional total return momentum.",
    "mom_3m": "Three-month recent momentum without skip month.",
    "multi_horizon": "Weighted 1/3/6/12-month multi-horizon momentum composite.",
    "vol_adjusted": "Six-month momentum scaled by recent annualized volatility.",
    "risk_adjusted": "Rolling Sharpe-like annualized return divided by volatility.",
    "dual_momentum": "Relative momentum penalized when absolute trend is below the 200-day average.",
    "ma_trend": "Trend persistence from price/MA200 and MA50/MA200 structure.",
    "drawdown_aware": "Six-month momentum penalized by recent drawdown from rolling high.",
    "reversal_adjusted": "12-1 momentum adjusted for short-term reversal risk.",
}


def compute_factor_scores(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {name: fn(prices).replace([np.inf, -np.inf], np.nan) for name, fn in FACTOR_DEFINITIONS.items()}
