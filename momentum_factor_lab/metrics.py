from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def max_drawdown(returns: pd.Series) -> float:
    returns = returns.dropna()
    if returns.empty:
        return 0.0
    equity = pd.concat([pd.Series([1.0]), (1.0 + returns).cumprod().reset_index(drop=True)], ignore_index=True)
    drawdown = equity / equity.cummax() - 1.0
    return float(drawdown.min())


def cagr(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    returns = returns.dropna()
    if returns.empty:
        return 0.0
    total = float((1.0 + returns).prod())
    years = max(len(returns) / periods_per_year, 1e-9)
    if total <= 0:
        return -1.0
    return total ** (1.0 / years) - 1.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=0) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate / TRADING_DAYS
    vol = excess.std(ddof=0)
    if vol == 0 or pd.isna(vol):
        return 0.0
    return float(excess.mean() / vol * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate / TRADING_DAYS
    downside = excess[excess < 0]
    downside_dev = downside.std(ddof=0)
    if downside.empty or downside_dev == 0 or pd.isna(downside_dev):
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside_dev * np.sqrt(TRADING_DAYS))


def calmar_ratio(returns: pd.Series) -> float:
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return float("inf") if cagr(returns) > 0 else 0.0
    return float(cagr(returns) / mdd)


def metric_summary(
    returns: pd.Series,
    turnover: pd.Series | None = None,
    costs: pd.Series | None = None,
) -> dict[str, float]:
    returns = returns.dropna()
    mdd = max_drawdown(returns)
    observations = float(len(returns))
    turnover_events = turnover.dropna() if turnover is not None else pd.Series(dtype=float)
    cost_series = costs.dropna() if costs is not None else pd.Series(dtype=float)
    total_turnover = float(turnover_events.sum()) if not turnover_events.empty else 0.0
    total_cost = float(cost_series.sum()) if not cost_series.empty else 0.0
    return {
        "cagr": cagr(returns),
        "annual_return": float(returns.mean() * TRADING_DAYS) if not returns.empty else 0.0,
        "volatility": annualized_volatility(returns),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "calmar": calmar_ratio(returns),
        "max_drawdown": mdd,
        "mdd": mdd,
        "avg_turnover": float(turnover_events.mean()) if not turnover_events.empty else 0.0,
        "total_turnover": total_turnover,
        "turnover_events": float(len(turnover_events)),
        "annualized_turnover": total_turnover / observations * TRADING_DAYS if observations else 0.0,
        "total_cost": total_cost,
        "avg_daily_cost": total_cost / observations if observations else 0.0,
        "annualized_cost_drag": total_cost / observations * TRADING_DAYS if observations else 0.0,
        "observations": observations,
    }
