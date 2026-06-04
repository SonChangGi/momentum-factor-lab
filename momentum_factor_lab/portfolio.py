from __future__ import annotations

import pandas as pd


def balanced_weights(
    scores: pd.Series,
    top_n: int = 15,
    max_weight: float = 0.10,
    long_only: bool = True,
) -> pd.Series:
    clean = scores.dropna().sort_values(ascending=False)
    if long_only:
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
