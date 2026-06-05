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


def two_month_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 42)


def skipped_two_month_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return total_return_momentum(prices, 42, skip=21)


def unskipped_six_month_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 126)


def deep_skip_twelve_month_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return total_return_momentum(prices, 252, skip=42)


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


def high_26week_proximity(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(126).max()) - 1.0


def breakout_63d(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(63).max()) - 1.0 + 0.5 * simple_momentum(prices, 21)


def breakout_126d(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(126).max()) - 1.0 + 0.5 * simple_momentum(prices, 63)


def reversal_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    long_mom = total_return_momentum(prices, 252, skip=21)
    short_reversal = simple_momentum(prices, 21)
    return long_mom - 0.35 * short_reversal


def acceleration_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    recent = simple_momentum(prices, 63)
    intermediate = total_return_momentum(prices, 126, skip=21)
    return recent - 0.5 * intermediate


def short_acceleration_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 21) - 0.5 * simple_momentum(prices, 63)


def decay_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    return total_return_momentum(prices, 126, skip=10) - 0.25 * simple_momentum(prices, 21).abs()


def consistency_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    positive_ratio = returns.gt(0).rolling(126).mean()
    return total_return_momentum(prices, 126, skip=10) * positive_ratio


def low_vol_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    momentum = total_return_momentum(prices, 126, skip=10)
    vol = prices.pct_change().rolling(63).std() * np.sqrt(TRADING_DAYS)
    return momentum - vol


def stability_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    momentum = total_return_momentum(prices, 126, skip=10)
    vol = prices.pct_change().rolling(126).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(momentum, 1.0 + vol)


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


def winsorized_skip_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change().shift(10)
    clipped = returns.clip(lower=-0.05, upper=0.05)
    return (1.0 + clipped).rolling(126).apply(np.prod, raw=True) - 1.0


def median_return_momentum(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    returns = prices.pct_change()
    return returns.rolling(window).median() * window


def price_efficiency_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    path_length = returns.abs().rolling(126).sum()
    direct_move = simple_momentum(prices, 126).abs()
    efficiency = _safe_div(direct_move, path_length)
    return total_return_momentum(prices, 126, skip=10) * efficiency


def range_position_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    rolling_low = prices.rolling(126).min()
    rolling_high = prices.rolling(126).max()
    range_position = _safe_div(prices - rolling_low, rolling_high - rolling_low) - 0.5
    return total_return_momentum(prices, 126, skip=10) + range_position


def winsorized_momentum(prices: pd.DataFrame, window: int, lower: float = -0.08, upper: float = 0.08) -> pd.DataFrame:
    returns = prices.pct_change().clip(lower=lower, upper=upper)
    return (1.0 + returns).rolling(window).apply(np.prod, raw=True) - 1.0


def volatility_adjusted_simple_momentum(prices: pd.DataFrame, lookback: int, vol_window: int) -> pd.DataFrame:
    momentum = simple_momentum(prices, lookback)
    vol = prices.pct_change().rolling(vol_window).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(momentum, vol)


def downside_adjusted_total_momentum(prices: pd.DataFrame, lookback: int, skip: int, downside_window: int) -> pd.DataFrame:
    returns = prices.pct_change()
    downside = returns.where(returns < 0, 0.0).rolling(downside_window).std() * np.sqrt(TRADING_DAYS)
    return _safe_div(total_return_momentum(prices, lookback, skip=skip), downside)


def moving_average_slope(prices: pd.DataFrame, window: int = 50, slope_window: int = 21) -> pd.DataFrame:
    ma = prices.rolling(window).mean()
    return ma.divide(ma.shift(slope_window)) - 1.0


def price_vs_ma200(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.divide(prices.rolling(200).mean()) - 1.0


def moving_average_stack_quality(prices: pd.DataFrame) -> pd.DataFrame:
    ma20 = prices.rolling(20).mean()
    ma50 = prices.rolling(50).mean()
    ma100 = prices.rolling(100).mean()
    ma200 = prices.rolling(200).mean()
    return (prices > ma20).astype(float) + (ma20 > ma50).astype(float) + (ma50 > ma100).astype(float) + (ma100 > ma200).astype(float)


def breakout_proximity(prices: pd.DataFrame, high_window: int, confirmation_window: int) -> pd.DataFrame:
    return prices.divide(prices.rolling(high_window).max()) - 1.0 + 0.5 * simple_momentum(prices, confirmation_window)


def acceleration_1m_vs_3m(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 21) - simple_momentum(prices, 63)


def acceleration_3m_vs_6m(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 63) - simple_momentum(prices, 126)


def acceleration_6m_vs_12m(prices: pd.DataFrame) -> pd.DataFrame:
    return simple_momentum(prices, 126) - simple_momentum(prices, 252)


def ulcer_adjusted_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    rolling_high = prices.rolling(126).max()
    drawdown = prices.divide(rolling_high) - 1.0
    ulcer = drawdown.pow(2).rolling(126).mean().pow(0.5)
    return _safe_div(total_return_momentum(prices, 126, skip=10), ulcer)


def smooth_return_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change()
    momentum = simple_momentum(prices, 126)
    smoothness_penalty = returns.rolling(126).std()
    return momentum - smoothness_penalty


def range_position_252d_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    rolling_low = prices.rolling(252).min()
    rolling_high = prices.rolling(252).max()
    range_position = _safe_div(prices - rolling_low, rolling_high - rolling_low) - 0.5
    return total_return_momentum(prices, 252, skip=21) + range_position


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
        FactorSpec("mom_12_2", "traditional", "P[t-42] / P[t-294] - 1", "Twelve-month momentum with a two-month skip to reduce reversal contamination.", "Independent raw-shift golden tests.", deep_skip_twelve_month_momentum),
        FactorSpec("mom_3_1", "traditional", "P[t-21] / P[t-84] - 1", "Traditional 3-1 skipped return momentum.", "Independent shifted-return and no-lookahead tests.", lambda p: total_return_momentum(p, 63, skip=21)),
        FactorSpec("mom_10d", "recent", "P[t] / P[t-10] - 1", "Ten-trading-day short-horizon momentum with high-turnover warning.", "Literal golden-vector simple-return tests and turnover warning audit.", lambda p: simple_momentum(p, 10)),
        FactorSpec("mom_6m_unskipped", "recent", "P[t] / P[t-126] - 1", "Six-month recent momentum without a skip window.", "Independent raw-shift golden tests.", unskipped_six_month_momentum),
        FactorSpec("mom_3m", "recent", "P[t] / P[t-63] - 1", "Three-month recent momentum without skip month.", "Simple-return fixture tests.", lambda p: simple_momentum(p, 63)),
        FactorSpec("mom_2m", "recent", "P[t] / P[t-42] - 1", "Two-month short-horizon momentum for fast leadership changes.", "Independent raw-shift golden tests.", two_month_momentum),
        FactorSpec("mom_2_1", "recent", "P[t-21] / P[t-63] - 1", "Two-month momentum that skips the most recent month.", "Independent raw-shift golden tests.", skipped_two_month_momentum),
        FactorSpec("mom_6m", "recent", "P[t] / P[t-126] - 1", "Six-month simple momentum without skip month.", "Independent simple-return and no-lookahead tests.", lambda p: simple_momentum(p, 126)),
        FactorSpec("mom_12m", "recent", "P[t] / P[t-252] - 1", "Twelve-month simple momentum without skip month.", "Independent simple-return and no-lookahead tests.", lambda p: simple_momentum(p, 252)),
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
        FactorSpec("high_26w", "drawdown", "P / rolling_high_126 - 1", "Closeness to a 26-week high for intermediate breakout confirmation.", "Independent rolling-high golden tests.", high_26week_proximity),
        FactorSpec("breakout_63d", "breakout", "P/rolling_high_63 - 1 + 0.5*1m", "Recent breakout pressure with one-month confirmation.", "Rolling-high plus 1m fixture tests.", breakout_63d),
        FactorSpec("breakout_126d", "breakout", "P/rolling_high_126 - 1 + 0.5*3m", "Intermediate breakout pressure with three-month confirmation.", "Independent rolling-high golden tests.", breakout_126d),
        FactorSpec("reversal_adjusted", "reversal", "12-1 momentum - 0.35*1m momentum", "12-1 momentum adjusted for short-term reversal risk.", "Component helper tests plus no-lookahead audit.", reversal_adjusted_momentum),
        FactorSpec("acceleration", "acceleration", "3m momentum - 0.5*6-1 momentum", "Momentum acceleration toward recent leadership.", "Manual acceleration fixture tests.", acceleration_momentum),
        FactorSpec("short_acceleration", "acceleration", "1m momentum - 0.5*3m momentum", "Short-horizon acceleration signal for very recent leadership surges.", "Independent raw-shift golden tests.", short_acceleration_momentum),
        FactorSpec("decay_adjusted", "acceleration", "6m(skip10) - 0.25*abs(1m momentum)", "Six-month momentum penalized when very recent moves look overextended.", "Independent raw-shift golden tests.", decay_adjusted_momentum),
        FactorSpec("consistency", "quality", "6m(skip10) * rolling_positive_return_ratio_126d", "Rewards momentum earned consistently across days.", "Positive-ratio fixture tests.", consistency_momentum),
        FactorSpec("low_vol_momentum", "risk_adjusted", "6m(skip10) - annualized_vol_63d", "Momentum penalized by high recent volatility.", "Low-vol ranking fixture tests.", low_vol_momentum),
        FactorSpec("stability_adjusted", "risk_adjusted", "6m(skip10) / (1 + annualized_vol_126d)", "Six-month momentum damped by one-year realized volatility from price returns.", "Independent volatility golden tests.", stability_adjusted_momentum),
        FactorSpec("relative_strength_6m", "cross_sectional", "cross-sectional percentile_rank(6m(skip10))", "Six-month relative-strength percentile within the eligible universe.", "Cross-sectional rank audit.", relative_strength_6m),
        FactorSpec("trend_quality", "quality", "P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126", "Combines trend slope with smoothness of returns.", "Rolling helper and finite audit.", trend_quality),
        FactorSpec("gap_resistant", "robust", "compound clipped daily returns over 126d", "Momentum using clipped daily returns to reduce single-gap dominance.", "Clipped-return fixture tests.", gap_resistant_momentum),
        FactorSpec("winsorized_skip", "robust", "compound clipped daily returns over 126d after 10d skip", "Skipped six-month momentum using winsorized daily returns to reduce gap dominance.", "Independent clipped-return golden tests.", winsorized_skip_momentum),
        FactorSpec("price_efficiency", "quality", "6m(skip10) * |P/P[t-126]-1| / sum_126(|daily_return|)", "Rewards six-month momentum that traveled a direct, low-chop price path.", "Path-efficiency fixture tests and division-by-zero audit.", price_efficiency_momentum),
        FactorSpec("range_position", "range", "6m(skip10) + (P-low_126)/(high_126-low_126) - 0.5", "Combines six-month momentum with where price sits inside its trailing range.", "Rolling-range fixture tests and flat-range audit.", range_position_momentum),
        FactorSpec("range_position_252d", "range", "12m(skip21) + (P-low_252)/(high_252-low_252) - 0.5", "Combines long-horizon skipped momentum with position inside a 52-week range.", "Independent rolling-range golden tests.", range_position_252d_momentum),
        FactorSpec("median_return_3m", "robust", "median(daily_return, 63d) * 63", "Three-month median daily return momentum to reduce outlier sensitivity.", "Median-return golden-vector and outlier-gap tests.", lambda p: median_return_momentum(p, 63)),
        FactorSpec("median_return_6m", "robust", "median(daily_return, 126d) * 126", "Six-month median daily return momentum to reduce outlier sensitivity.", "Median-return golden-vector and no-lookahead tests.", lambda p: median_return_momentum(p, 126)),
        FactorSpec("winsorized_3m", "robust", "compound clipped [-8%, +8%] daily returns over 63d", "Three-month winsorized compounded momentum.", "Winsorized golden-vector and outlier-gap tests.", lambda p: winsorized_momentum(p, 63)),
        FactorSpec("winsorized_12m", "robust", "compound clipped [-8%, +8%] daily returns over 252d", "Twelve-month winsorized compounded momentum.", "Winsorized no-lookahead and edge-case tests.", lambda p: winsorized_momentum(p, 252)),
        FactorSpec("vol_adjusted_3m", "risk_adjusted", "3m simple momentum / annualized_vol_63d", "Three-month momentum scaled by recent annualized volatility.", "Division-by-zero and finite coverage audit.", lambda p: volatility_adjusted_simple_momentum(p, 63, 63)),
        FactorSpec("vol_adjusted_12m", "risk_adjusted", "12-1 momentum / annualized_vol_126d", "Twelve-minus-one momentum scaled by intermediate volatility.", "Division-by-zero and no-lookahead audit.", lambda p: _safe_div(total_return_momentum(p, 252, skip=21), p.pct_change().rolling(126).std() * np.sqrt(TRADING_DAYS))),
        FactorSpec("downside_adjusted_12m", "risk_adjusted", "12-1 momentum / annualized_downside_vol_252d", "Twelve-minus-one momentum scaled by downside volatility.", "Downside risk edge-case tests.", lambda p: downside_adjusted_total_momentum(p, 252, 21, 252)),
        FactorSpec("ma_slope_50", "trend", "MA50[t] / MA50[t-21] - 1", "One-month slope of the 50-day moving average.", "Moving-average slope fixture tests.", moving_average_slope),
        FactorSpec("price_vs_ma200", "trend", "P / MA200 - 1", "Distance of price above/below the 200-day moving average.", "Moving-average fixture tests.", price_vs_ma200),
        FactorSpec("ma_stack_quality", "trend", "I(P>MA20)+I(MA20>MA50)+I(MA50>MA100)+I(MA100>MA200)", "Four-step moving-average stack quality score.", "Bounded 0..4 output and no-lookahead audit.", moving_average_stack_quality),
        FactorSpec("breakout_20d", "breakout", "P/rolling_high_20 - 1 + 0.5*10d", "Short breakout proximity with ten-day confirmation.", "Rolling-high golden-vector tests.", lambda p: breakout_proximity(p, 20, 10)),
        FactorSpec("accel_1m_vs_3m", "acceleration", "1m momentum - 3m momentum", "Acceleration from three-month to one-month leadership.", "Manual acceleration fixture tests.", acceleration_1m_vs_3m),
        FactorSpec("accel_3m_vs_6m", "acceleration", "3m momentum - 6m momentum", "Acceleration from six-month to three-month leadership.", "Manual acceleration fixture tests.", acceleration_3m_vs_6m),
        FactorSpec("accel_6m_vs_12m", "acceleration", "6m momentum - 12m momentum", "Acceleration from twelve-month to six-month leadership.", "Manual acceleration fixture tests.", acceleration_6m_vs_12m),
        FactorSpec("ulcer_adjusted", "drawdown", "6m(skip10) / sqrt(mean(drawdown_126^2, 126d))", "Momentum scaled by Ulcer-style drawdown severity.", "Drawdown denominator and finite audit.", ulcer_adjusted_momentum),
        FactorSpec("smooth_return_6m", "quality", "6m simple momentum - rolling_std_daily_return_126d", "Six-month return momentum penalized by daily return roughness.", "Smoothness edge-case tests.", smooth_return_momentum),
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
