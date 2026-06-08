from __future__ import annotations

import numpy as np
import pandas as pd


WEIGHTING_DIAGNOSTIC_COLUMNS = [
    "weighting_method",
    "score_component",
    "market_cap",
    "market_cap_source",
    "market_cap_component",
    "liquidity_component",
    "size_component_source",
    "raw_weight_score",
    "pre_cap_weight",
    "weight_cap",
    "weight_cap_excess",
]


def balanced_weights(
    scores: pd.Series,
    top_n: int = 15,
    max_weight: float = 0.10,
    require_positive: bool = False,
) -> pd.Series:
    clean = scores.dropna().sort_values(ascending=False)
    if require_positive:
        clean = clean[clean > 0]
    selected = clean.head(top_n)
    weights = pd.Series(0.0, index=scores.index, dtype=float)
    if selected.empty:
        return weights
    base = min(1.0 / len(selected), max_weight)
    weights.loc[selected.index] = base
    total = weights.sum()
    if total > 1.0:
        weights /= total
    return weights


def recommendation_table(scores: pd.Series, weights: pd.Series, top_n: int = 20) -> pd.DataFrame:
    ranked = scores.dropna().sort_values(ascending=False).head(top_n)
    frame = pd.DataFrame({"symbol": ranked.index, "score": ranked.values})
    frame["weight"] = frame["symbol"].map(weights).fillna(0.0).values
    frame["rank"] = range(1, len(frame) + 1)
    return frame[["rank", "symbol", "score", "weight"]]


def _finite_positive(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)
    return values.where(values > 0)


def _percentile_component(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)
    valid = values.dropna()
    if valid.empty:
        return pd.Series(0.0, index=series.index, dtype=float)
    return values.rank(pct=True, ascending=True).fillna(0.0).astype(float)


def _score_component(scores: pd.Series) -> pd.Series:
    values = pd.to_numeric(scores, errors="coerce").astype(float).replace([np.inf, -np.inf], np.nan)
    positive = values.clip(lower=0.0)
    if positive.dropna().gt(0).any():
        return _percentile_component(positive)
    return _percentile_component(values)


def _iterative_cap(weights: pd.Series, max_weight: float) -> pd.Series:
    capped = weights.clip(lower=0.0).fillna(0.0).astype(float).copy()
    if capped.empty or max_weight <= 0:
        return pd.Series(0.0, index=weights.index, dtype=float)
    total = float(capped.sum())
    if total <= 0:
        return pd.Series(0.0, index=weights.index, dtype=float)
    capped /= total
    for _ in range(len(capped) + 1):
        over = capped > max_weight
        if not over.any():
            break
        excess = float((capped.loc[over] - max_weight).sum())
        capped.loc[over] = max_weight
        under = ~over
        under_total = float(capped.loc[under].sum())
        if excess <= 0 or under_total <= 0:
            break
        capacity = max_weight - capped.loc[under]
        expandable = capacity > 1e-15
        if not expandable.any():
            break
        base = capped.loc[under][expandable]
        base_total = float(base.sum())
        if base_total <= 0:
            capped.loc[base.index] += excess / len(base)
        else:
            capped.loc[base.index] += excess * base / base_total
    return capped.clip(lower=0.0, upper=max_weight).astype(float)


def evidence_weighted_recommendation_table(
    recommendations: pd.DataFrame,
    *,
    max_weight: float,
    score_weight: float = 0.60,
    market_cap_weight: float = 0.25,
    liquidity_weight: float = 0.15,
    rank_floor: float = 0.05,
    method: str = "score_size_liquidity",
) -> pd.DataFrame:
    """Return recommendation rows with evidence-weighted current allocation diagnostics.

    This intentionally applies only to final current recommendation rows. Historical
    factor backtests keep their comparable capped equal top-N construction.
    """

    frame = recommendations.copy()
    if frame.empty:
        for column in WEIGHTING_DIAGNOSTIC_COLUMNS:
            if column not in frame:
                frame[column] = pd.Series(dtype=object if column.endswith("source") or column == "weighting_method" else float)
        return frame

    component_weights = pd.Series(
        {
            "score": float(score_weight),
            "market_cap": float(market_cap_weight),
            "liquidity": float(liquidity_weight),
        }
    )
    if component_weights.lt(0).any():
        raise ValueError("recommendation weighting component weights must be non-negative")
    if float(component_weights.sum()) <= 0:
        raise ValueError("at least one recommendation weighting component must be positive")
    if rank_floor < 0:
        raise ValueError("recommendation_rank_floor must be non-negative")

    frame["weighting_method"] = method
    frame["score_component"] = _score_component(frame["score"])

    if "market_cap" not in frame:
        frame["market_cap"] = np.nan
    market_cap = _finite_positive(frame["market_cap"])
    market_cap_available = market_cap.notna()
    default_market_cap_source = pd.Series(
        np.where(market_cap_available, "provided", "unavailable"), index=frame.index
    )
    if "market_cap_source" not in frame:
        frame["market_cap_source"] = default_market_cap_source
    else:
        frame["market_cap_source"] = frame["market_cap_source"].fillna(default_market_cap_source)
    frame.loc[~market_cap_available, "market_cap_source"] = frame.loc[
        ~market_cap_available, "market_cap_source"
    ].where(
        frame.loc[~market_cap_available, "market_cap_source"]
        .astype(str)
        .str.startswith(("unavailable", "disabled")),
        "unavailable",
    )
    frame["market_cap_component"] = _percentile_component(np.log1p(market_cap))

    if "avg_dollar_volume_63d" in frame:
        liquidity = _finite_positive(frame["avg_dollar_volume_63d"])
    else:
        liquidity = pd.Series(np.nan, index=frame.index, dtype=float)
    frame["liquidity_component"] = _percentile_component(np.log1p(liquidity))
    has_liquidity = liquidity.notna()
    frame["size_component_source"] = np.where(
        market_cap_available,
        "market_cap",
        np.where(has_liquidity, "liquidity_proxy_63d_adv", "rank_score_only"),
    )

    raw = pd.Series(float(rank_floor), index=frame.index, dtype=float)
    raw += component_weights["score"] * frame["score_component"].astype(float)

    market_cap_term = component_weights["market_cap"] * frame["market_cap_component"].astype(float).where(
        market_cap_available, 0.0
    )
    liquidity_weight_by_row = component_weights["liquidity"] + component_weights["market_cap"] * (
        ~market_cap_available
    ).astype(float)
    liquidity_term = liquidity_weight_by_row * frame["liquidity_component"].astype(float)
    raw += market_cap_term + liquidity_term
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(float(rank_floor)).clip(lower=0.0)
    if float(raw.sum()) <= 0:
        raw = pd.Series(1.0, index=frame.index, dtype=float)
    frame["raw_weight_score"] = raw
    frame["pre_cap_weight"] = raw / float(raw.sum())
    capped = _iterative_cap(frame["pre_cap_weight"], max_weight)
    frame["weight"] = capped.values
    frame["weight_cap"] = float(max_weight)
    frame["weight_cap_excess"] = (frame["pre_cap_weight"] - frame["weight"]).clip(lower=0.0)
    return frame
