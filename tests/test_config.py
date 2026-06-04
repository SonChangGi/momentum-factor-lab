import pytest

from momentum_factor_lab.config import RunConfig


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"top_n": 0}, "top_n"),
        ({"max_weight": 0}, "max_weight"),
        ({"max_weight": -0.1}, "max_weight"),
        ({"max_weight": 1.5}, "max_weight"),
        ({"transaction_cost_bps": -1}, "transaction_cost_bps"),
        ({"slippage_bps": -1}, "slippage_bps"),
        ({"start_date": "2025-01-02", "end_date": "2025-01-01"}, "start_date"),
    ],
)
def test_config_validation_rejects_invalid_risk_inputs(kwargs, message):
    config = RunConfig(**kwargs)
    with pytest.raises(ValueError, match=message):
        config.validate()
