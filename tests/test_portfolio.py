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
