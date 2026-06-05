import pandas as pd

from momentum_factor_lab.backtest import BacktestResult
from momentum_factor_lab.workflow import _percentile, _score_factors
from momentum_factor_lab.workflow import _metrics_for_backtests


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


def test_metrics_for_backtests_slices_turnover_and_costs_by_return_window():
    dates = pd.bdate_range("2024-01-01", periods=10)
    result = BacktestResult(
        factor_name="test",
        returns=pd.Series([0.01] * len(dates), index=dates, name="test"),
        equity=pd.Series([1.0] * len(dates), index=dates, name="test"),
        weights=pd.DataFrame(index=dates),
        turnover=pd.Series([0.2, 0.8], index=[dates[1], dates[8]], name="test"),
        costs=pd.Series([0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.04], index=dates, name="test"),
        signal_dates=pd.Series(dtype="datetime64[ns]", name="signal_date"),
    )

    metrics, robustness = _metrics_for_backtests({"test": result})
    row = metrics.loc["test"]

    assert row["full_total_turnover"] == 1.0
    assert row["train_total_turnover"] == 0.2
    assert row["validation_total_turnover"] == 0.8
    assert row["full_total_cost"] == 0.05
    assert row["train_total_cost"] == 0.01
    assert row["validation_total_cost"] == 0.04
    validation = robustness[robustness["slice"].eq("validation")].iloc[0]
    assert validation["total_turnover"] == 0.8
    assert validation["total_cost"] == 0.04
