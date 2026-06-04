import pandas as pd

from momentum_factor_lab.workflow import _percentile, _score_factors


def test_percentile_rewards_higher_values_when_requested():
    scores = _percentile(pd.Series({"weak": 1.0, "strong": 3.0}), higher_is_better=True)
    assert scores["strong"] > scores["weak"]


def test_percentile_rewards_lower_values_when_requested():
    scores = _percentile(pd.Series({"low_turnover": 0.1, "high_turnover": 0.9}), higher_is_better=False)
    assert scores["low_turnover"] > scores["high_turnover"]


def test_score_factors_prefers_validation_strength_and_lower_turnover():
    metrics = pd.DataFrame(
        {
            "validation_sharpe": {"good": 2.0, "bad": 0.2},
            "validation_sortino": {"good": 3.0, "bad": 0.3},
            "validation_calmar": {"good": 1.5, "bad": 0.1},
            "validation_max_drawdown": {"good": -0.05, "bad": -0.40},
            "validation_cagr": {"good": 0.20, "bad": 0.01},
            "full_avg_turnover": {"good": 0.1, "bad": 1.0},
            "train_sharpe": {"good": 2.1, "bad": 0.1},
        }
    )
    ranked = _score_factors(metrics)
    assert ranked.index[0] == "good"
