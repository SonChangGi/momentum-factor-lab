import pandas as pd

from momentum_factor_lab.portfolio import balanced_weights, recommendation_table


def test_balanced_weights_long_only_and_cap():
    scores = pd.Series({"A": 3.0, "B": 2.0, "C": -1.0, "D": 1.0})
    weights = balanced_weights(scores, top_n=3, max_weight=0.4)
    assert weights["C"] == 0.0
    assert weights.max() <= 0.4
    assert abs(weights.sum() - 1.0) < 1e-12


def test_recommendation_table_contains_weights_and_ranks():
    scores = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
    weights = balanced_weights(scores, top_n=2, max_weight=0.5)
    table = recommendation_table(scores, weights, top_n=2)
    assert list(table["symbol"]) == ["A", "B"]
    assert list(table["rank"]) == [1, 2]
    assert table["weight"].sum() == 1.0


def test_balanced_weights_selects_only_top_20():
    scores = pd.Series({f"S{i:02d}": float(100 - i) for i in range(30)})
    weights = balanced_weights(scores, top_n=20, max_weight=0.05)
    assert weights.gt(0).sum() == 20
    assert weights["S20"] == 0.0


def test_balanced_weights_top_20_includes_negative_scores_by_rank():
    scores = pd.Series({f"S{i:02d}": float(10 - i) for i in range(25)})
    weights = balanced_weights(scores, top_n=20, max_weight=0.05)
    assert weights.gt(0).sum() == 20
    assert weights["S19"] > 0
    assert weights["S20"] == 0.0
    assert abs(weights.sum() - 1.0) < 1e-12
