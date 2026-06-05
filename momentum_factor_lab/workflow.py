from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import disclaimers
from .backtest import BacktestResult, run_factor_backtest
from .config import RunConfig
from .data import MarketData, load_market_data
from .factors import FACTOR_DESCRIPTIONS, compute_factor_scores, factor_definitions_frame, simple_momentum, total_return_momentum, validate_factor_library
from .metrics import TRADING_DAYS, annualized_volatility, metric_summary
from .portfolio import balanced_weights, recommendation_table


@dataclass(slots=True)
class RunResult:
    config: RunConfig
    market_data: MarketData
    factor_scores: dict[str, pd.DataFrame]
    backtests: dict[str, BacktestResult]
    metrics: pd.DataFrame
    score_components: pd.DataFrame
    selected_factor: str
    selected_reason: str
    recommendations: pd.DataFrame
    robustness: pd.DataFrame
    sensitivity: pd.DataFrame
    benchmark_relative: pd.DataFrame
    factor_validation: pd.DataFrame
    factor_definitions: pd.DataFrame
    data_sources: pd.DataFrame
    metadata: dict[str, Any]
    output_paths: dict[str, str]


def _slice_returns(returns: pd.Series, split_at: int) -> dict[str, pd.Series]:
    if returns.empty:
        return {"full": returns, "train": returns, "validation": returns, "recent": returns}
    split_at = min(max(split_at, 1), len(returns) - 1)
    recent_start = max(0, len(returns) - 504)
    return {
        "full": returns,
        "train": returns.iloc[:split_at],
        "validation": returns.iloc[split_at:],
        "recent": returns.iloc[recent_start:],
    }


def _metrics_for_backtests(backtests: dict[str, BacktestResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    robustness_rows = []
    for name, result in backtests.items():
        split_at = int(len(result.returns) * 0.70)
        slices = _slice_returns(result.returns, split_at)
        full = metric_summary(slices["full"], result.turnover)
        train = metric_summary(slices["train"], result.turnover)
        validation = metric_summary(slices["validation"], result.turnover)
        row = {"factor": name, **{f"full_{k}": v for k, v in full.items()}}
        row.update({f"train_{k}": v for k, v in train.items()})
        row.update({f"validation_{k}": v for k, v in validation.items()})
        rows.append(row)
        for slice_name, series in slices.items():
            m = metric_summary(series, result.turnover)
            robustness_rows.append({"factor": name, "slice": slice_name, **m})
    return pd.DataFrame(rows).set_index("factor"), pd.DataFrame(robustness_rows)


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    finite = series.replace([np.inf, -np.inf], np.nan)
    values = finite.fillna(finite.median())
    ranks = values.rank(pct=True, ascending=higher_is_better)
    return ranks.fillna(0.0)


def _score_factors(metrics: pd.DataFrame) -> pd.DataFrame:
    components = pd.DataFrame(index=metrics.index)
    components["validation_sharpe"] = _percentile(metrics["validation_sharpe"], True)
    components["validation_sortino"] = _percentile(metrics["validation_sortino"], True)
    components["validation_calmar"] = _percentile(metrics["validation_calmar"], True)
    components["validation_mdd"] = _percentile(metrics["validation_max_drawdown"], True)
    components["validation_cagr"] = _percentile(metrics["validation_cagr"], True)
    components["turnover_penalty"] = _percentile(metrics["full_avg_turnover"], False)
    components["train_validation_stability"] = 1.0 - (
        metrics["train_sharpe"].replace([np.inf, -np.inf], np.nan).fillna(0)
        - metrics["validation_sharpe"].replace([np.inf, -np.inf], np.nan).fillna(0)
    ).abs().rank(pct=True)
    components["composite_score"] = components.mean(axis=1)
    return components.sort_values("composite_score", ascending=False)


def _benchmark_relative_metrics(backtests: dict[str, BacktestResult], prices: pd.DataFrame, config: RunConfig) -> pd.DataFrame:
    columns = [
        "factor",
        "benchmark",
        "strategy_cagr",
        "benchmark_cagr",
        "strategy_sharpe",
        "benchmark_sharpe",
        "strategy_max_drawdown",
        "benchmark_max_drawdown",
        "annualized_excess_return",
        "tracking_error",
        "information_ratio",
        "beta_to_benchmark",
    ]
    if config.benchmark not in prices:
        return pd.DataFrame(columns=columns)

    benchmark_returns = prices[config.benchmark].pct_change().fillna(0.0).rename("benchmark")
    rows: list[dict[str, float | str]] = []
    for name, result in backtests.items():
        aligned = pd.concat([result.returns.rename("strategy"), benchmark_returns], axis=1).dropna()
        if aligned.empty:
            continue
        strategy_metrics = metric_summary(aligned["strategy"], result.turnover)
        benchmark_metrics = metric_summary(aligned["benchmark"])
        excess = aligned["strategy"] - aligned["benchmark"]
        tracking_error = annualized_volatility(excess)
        annualized_excess_return = float(excess.mean() * TRADING_DAYS)
        benchmark_var = float(aligned["benchmark"].var(ddof=0))
        beta = float(aligned["strategy"].cov(aligned["benchmark"]) / benchmark_var) if benchmark_var > 0 else 0.0
        rows.append(
            {
                "factor": name,
                "benchmark": config.benchmark,
                "strategy_cagr": strategy_metrics["cagr"],
                "benchmark_cagr": benchmark_metrics["cagr"],
                "strategy_sharpe": strategy_metrics["sharpe"],
                "benchmark_sharpe": benchmark_metrics["sharpe"],
                "strategy_max_drawdown": strategy_metrics["max_drawdown"],
                "benchmark_max_drawdown": benchmark_metrics["max_drawdown"],
                "annualized_excess_return": annualized_excess_return,
                "tracking_error": tracking_error,
                "information_ratio": annualized_excess_return / tracking_error if tracking_error > 0 else 0.0,
                "beta_to_benchmark": beta,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _rolling_risk_adjusted(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    returns = prices.pct_change()
    mean = returns.rolling(window).mean() * TRADING_DAYS
    vol = returns.rolling(window).std() * np.sqrt(TRADING_DAYS)
    return mean.divide(vol.replace(0, np.nan))


def _multi_horizon_variant(prices: pd.DataFrame, weights: tuple[float, float, float, float]) -> pd.DataFrame:
    w1, w3, w6, w12 = weights
    return (
        w1 * simple_momentum(prices, 21)
        + w3 * total_return_momentum(prices, 63, skip=5)
        + w6 * total_return_momentum(prices, 126, skip=10)
        + w12 * total_return_momentum(prices, 252, skip=21)
    )


def _vol_adjusted_variant(prices: pd.DataFrame, lookback: int, skip: int, vol_window: int) -> pd.DataFrame:
    momentum = total_return_momentum(prices, lookback, skip=skip)
    vol = prices.pct_change().rolling(vol_window).std() * np.sqrt(TRADING_DAYS)
    return momentum.divide(vol.replace(0, np.nan))


def _ma_trend_variant(prices: pd.DataFrame, short_window: int, long_window: int) -> pd.DataFrame:
    short_ma = prices.rolling(short_window).mean()
    long_ma = prices.rolling(long_window).mean()
    return prices.divide(long_ma) - 1.0 + 0.5 * (short_ma.divide(long_ma) - 1.0)


def _dual_momentum_variant(prices: pd.DataFrame, lookback: int, skip: int, trend_window: int) -> pd.DataFrame:
    relative = total_return_momentum(prices, lookback, skip=skip)
    absolute = prices.divide(prices.rolling(trend_window).mean()) - 1.0
    return relative.where(absolute > 0, relative - absolute.abs() - 1.0)


def _drawdown_aware_variant(prices: pd.DataFrame, lookback: int, skip: int) -> pd.DataFrame:
    momentum = total_return_momentum(prices, lookback, skip=skip)
    drawdown = prices.divide(prices.rolling(lookback).max()) - 1.0
    return momentum + drawdown


def _reversal_adjusted_variant(prices: pd.DataFrame, penalty: float) -> pd.DataFrame:
    long_mom = total_return_momentum(prices, 252, skip=21)
    short_reversal = simple_momentum(prices, 21)
    return long_mom - penalty * short_reversal


def _selected_factor_variants(
    prices: pd.DataFrame,
    selected_factor: str,
    base_scores: pd.DataFrame,
) -> list[tuple[str, pd.DataFrame, str]]:
    variants: list[tuple[str, pd.DataFrame, str]] = [("base", base_scores, "original selected factor parameters")]
    if selected_factor == "mom_12_1":
        for lookback, skip in [(210, 21), (252, 10), (252, 42), (294, 21)]:
            variants.append((f"lookback_{lookback}_skip_{skip}", total_return_momentum(prices, lookback, skip), f"lookback={lookback}; skip={skip}"))
    elif selected_factor == "mom_6_1":
        for lookback, skip in [(105, 21), (126, 10), (126, 42), (147, 21)]:
            variants.append((f"lookback_{lookback}_skip_{skip}", total_return_momentum(prices, lookback, skip), f"lookback={lookback}; skip={skip}"))
    elif selected_factor == "mom_3m":
        for lookback in [42, 84, 105]:
            variants.append((f"lookback_{lookback}", simple_momentum(prices, lookback), f"lookback={lookback}; skip=0"))
    elif selected_factor == "multi_horizon":
        for label, weights in [
            ("short_tilt", (0.25, 0.30, 0.25, 0.20)),
            ("long_tilt", (0.10, 0.20, 0.30, 0.40)),
            ("no_1m", (0.00, 0.30, 0.35, 0.35)),
        ]:
            variants.append((label, _multi_horizon_variant(prices, weights), f"weights_1m_3m_6m_12m={weights}"))
    elif selected_factor == "vol_adjusted":
        for lookback, skip, vol_window in [(105, 10, 42), (126, 21, 63), (147, 10, 84)]:
            variants.append((f"lookback_{lookback}_skip_{skip}_vol_{vol_window}", _vol_adjusted_variant(prices, lookback, skip, vol_window), f"lookback={lookback}; skip={skip}; vol_window={vol_window}"))
    elif selected_factor == "risk_adjusted":
        for window in [84, 168, 210]:
            variants.append((f"window_{window}", _rolling_risk_adjusted(prices, window), f"rolling_window={window}"))
    elif selected_factor == "dual_momentum":
        for lookback, skip, trend_window in [(105, 10, 160), (126, 21, 200), (147, 21, 252)]:
            variants.append((f"lookback_{lookback}_skip_{skip}_trend_{trend_window}", _dual_momentum_variant(prices, lookback, skip, trend_window), f"lookback={lookback}; skip={skip}; trend_window={trend_window}"))
    elif selected_factor == "ma_trend":
        for short_window, long_window in [(40, 160), (63, 200), (63, 252), (100, 200)]:
            variants.append((f"ma_{short_window}_{long_window}", _ma_trend_variant(prices, short_window, long_window), f"short_ma={short_window}; long_ma={long_window}"))
    elif selected_factor == "drawdown_aware":
        for lookback, skip in [(105, 10), (126, 21), (147, 21)]:
            variants.append((f"lookback_{lookback}_skip_{skip}", _drawdown_aware_variant(prices, lookback, skip), f"lookback={lookback}; skip={skip}"))
    elif selected_factor == "reversal_adjusted":
        for penalty in [0.20, 0.50, 0.65]:
            variants.append((f"penalty_{penalty}", _reversal_adjusted_variant(prices, penalty), f"short_reversal_penalty={penalty}"))
    return [(name, scores.replace([np.inf, -np.inf], np.nan), params) for name, scores, params in variants]


def _parameter_sensitivity(
    prices: pd.DataFrame,
    selected_factor: str,
    config: RunConfig,
    base_scores: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, scores, parameter_set in _selected_factor_variants(prices, selected_factor, base_scores):
        result = run_factor_backtest(prices, scores, config, f"{selected_factor}:{variant}")
        rows.append(
            {
                "factor": selected_factor,
                "variant_type": "factor_parameter",
                "variant": variant,
                "parameter_set": parameter_set,
                **metric_summary(result.returns, result.turnover),
            }
        )

    top_n_candidates = sorted({max(5, config.top_n - 5), config.top_n, config.top_n + 5})
    max_weight_candidates = sorted({max(0.02, round(config.max_weight - 0.02, 4)), config.max_weight, min(0.20, round(config.max_weight + 0.02, 4))})
    for top_n in top_n_candidates:
        if top_n == config.top_n:
            continue
        result = run_factor_backtest(prices, base_scores, replace(config, top_n=top_n), f"{selected_factor}:top_n_{top_n}")
        rows.append(
            {
                "factor": selected_factor,
                "variant_type": "portfolio_parameter",
                "variant": f"top_n_{top_n}",
                "parameter_set": f"top_n={top_n}; max_weight={config.max_weight}",
                **metric_summary(result.returns, result.turnover),
            }
        )
    for max_weight in max_weight_candidates:
        if max_weight == config.max_weight:
            continue
        result = run_factor_backtest(prices, base_scores, replace(config, max_weight=max_weight), f"{selected_factor}:max_weight_{max_weight}")
        rows.append(
            {
                "factor": selected_factor,
                "variant_type": "portfolio_parameter",
                "variant": f"max_weight_{max_weight}",
                "parameter_set": f"top_n={config.top_n}; max_weight={max_weight}",
                **metric_summary(result.returns, result.turnover),
            }
        )
    return pd.DataFrame(rows).sort_values(["variant_type", "variant"]).reset_index(drop=True)


def _resolve_selected_factor(
    config: RunConfig,
    factor_scores: dict[str, pd.DataFrame],
    validation_selected_factor: str,
) -> tuple[str, str, str]:
    if config.selected_factor is None:
        return (
            validation_selected_factor,
            "validation_performance",
            (
                f"{validation_selected_factor} selected by validation-first composite score for "
                "research comparison only; fresh live recommendations require a predeclared "
                "selected_factor so current holdings are not chosen with same-sample validation performance."
            ),
        )

    selected_factor = config.selected_factor.strip()
    if selected_factor not in factor_scores:
        available = ", ".join(sorted(factor_scores))
        raise ValueError(f"selected_factor must be one of: {available}")
    return (
        selected_factor,
        "predeclared",
        (
            f"{selected_factor} selected from the predeclared/frozen run configuration; "
            "validation rankings are reported for audit and are not used to choose current recommendations."
        ),
    )


def _recommendation_status(config: RunConfig, market_data: MarketData, selection_source: str) -> tuple[str, bool]:
    if market_data.offline_sample:
        return ("sample_offline_not_current", False)
    if market_data.as_of is None:
        return ("live_unavailable", False)
    age_days = (pd.Timestamp(datetime.now(UTC).date()) - pd.Timestamp(market_data.as_of).normalize()).days
    if age_days > config.stale_after_days:
        return (f"stale_live_data_{age_days}_days_old", False)
    if selection_source != "predeclared":
        return ("live_selected_factor_required", False)
    return ("current_live", True)


def run_analysis(config: RunConfig) -> RunResult:
    config.validate()
    market_data = load_market_data(config)
    prices = market_data.prices.dropna(axis=1, how="all")
    factor_scores = compute_factor_scores(prices)
    factor_validation = validate_factor_library(prices)
    factor_definitions = factor_definitions_frame()
    backtests = {
        name: run_factor_backtest(prices, scores, config, name)
        for name, scores in factor_scores.items()
    }
    metrics, robustness = _metrics_for_backtests(backtests)
    benchmark_relative = _benchmark_relative_metrics(backtests, prices, config)
    score_components = _score_factors(metrics)
    validation_selected_factor = str(score_components.index[0])
    selected_factor, selection_source, selected_reason = _resolve_selected_factor(config, factor_scores, validation_selected_factor)
    latest_scores = factor_scores[selected_factor].iloc[-1].dropna()
    weights = balanced_weights(latest_scores, config.top_n, config.max_weight)
    recommendations = recommendation_table(latest_scores, weights, top_n=config.top_n)
    status, current_available = _recommendation_status(config, market_data, selection_source)
    subset_rows = market_data.data_sources[market_data.data_sources["source"].eq("live-run-summary")] if "source" in market_data.data_sources else pd.DataFrame()
    subset_run = bool(subset_rows["subset_run"].iloc[-1]) if not subset_rows.empty else market_data.offline_sample
    if subset_run and not market_data.offline_sample:
        requested = int(subset_rows["requested_price_symbols"].iloc[-1])
        candidates = int(subset_rows["candidate_symbols"].iloc[-1])
        status = f"{status}_subset_run_{requested}_of_{candidates}"
    if not current_available and not market_data.offline_sample:
        recommendations["weight"] = 0.0
    recommendations["recommendation_status"] = status
    recommendations["signal_date"] = str(prices.index.max().date()) if not prices.empty else "unavailable"
    recommendations["selected_factor"] = selected_factor
    recommendations["selected_factor_selection_source"] = selection_source

    sensitivity = _parameter_sensitivity(prices, selected_factor, config, factor_scores[selected_factor])
    metadata = {
        "run_timestamp_utc": datetime.now(UTC).isoformat(),
        "provider": market_data.provider,
        "offline_sample": market_data.offline_sample,
        "live_error": market_data.live_error,
        "data_as_of": str(market_data.as_of.date()) if market_data.as_of is not None else None,
        "recommendation_status": status,
        "current_recommendations_available": current_available,
        "selected_factor": selected_factor,
        "validation_selected_factor": validation_selected_factor,
        "selected_factor_selection_source": selection_source,
        "selected_factor_description": FACTOR_DESCRIPTIONS.get(selected_factor, selected_factor),
        "selected_reason": selected_reason,
        "signal_date": str(prices.index.max().date()) if not prices.empty else None,
        "execution_delay": "one trading day after signal/rebalance schedule",
        "portfolio_construction": f"long-only top-{config.top_n} factor portfolios at each rebalance, max weight {config.max_weight:.2%}",
        "candidate_universe_size": len(market_data.candidate_universe),
        "eligible_price_universe_size": len(prices.columns),
        "excluded_symbols": len(market_data.exclusions),
        "subset_run": subset_run,
        "factor_count": len(factor_definitions),
        "factor_validation_status": "pass" if factor_validation["status"].eq("pass").all() else "fail",
        "transaction_cost_bps": config.transaction_cost_bps,
        "slippage_bps": config.slippage_bps,
        "benchmark": config.benchmark,
        "survivorship_bias_caveat": disclaimers.DATA_LIMITATIONS,
        "non_advice_disclaimer": disclaimers.NON_ADVICE,
        "live_data_gate": disclaimers.LIVE_DATA_GATE,
    }
    return RunResult(
        config=config,
        market_data=market_data,
        factor_scores=factor_scores,
        backtests=backtests,
        metrics=metrics,
        score_components=score_components,
        selected_factor=selected_factor,
        selected_reason=selected_reason,
        recommendations=recommendations,
        robustness=robustness,
        sensitivity=sensitivity,
        benchmark_relative=benchmark_relative,
        factor_validation=factor_validation,
        factor_definitions=factor_definitions,
        data_sources=market_data.data_sources,
        metadata=metadata,
        output_paths={},
    )


def write_run_results_json(result: RunResult, path: Path) -> None:
    payload = {
        "metadata": result.metadata,
        "config": result.config.to_dict(),
        "selected_factor": result.selected_factor,
        "score_components": result.score_components.reset_index(names="factor").to_dict(orient="records"),
        "benchmark_relative": result.benchmark_relative.to_dict(orient="records"),
        "sensitivity": result.sensitivity.to_dict(orient="records"),
        "recommendations": result.recommendations.to_dict(orient="records"),
        "data_sources": result.data_sources.to_dict(orient="records"),
        "price_sources": result.market_data.price_sources.to_dict(orient="records"),
        "factor_validation": result.factor_validation.to_dict(orient="records"),
        "factor_definitions": result.factor_definitions.to_dict(orient="records"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
