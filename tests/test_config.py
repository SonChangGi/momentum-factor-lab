import pytest

from momentum_factor_lab.config import RunConfig


def test_config_defaults_to_top_20_and_large_universe():
    config = RunConfig()
    assert config.top_n == 20
    assert len(config.universe) >= 2000


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
        ({"max_price_symbols": 0}, "max_price_symbols"),
        ({"price_chunk_size": 0}, "price_chunk_size"),
        ({"stooq_fallback_limit": -1}, "stooq_fallback_limit"),
        ({"retry_count": -1}, "retry_count"),
        ({"min_price": -1}, "min_price"),
    ],
)
def test_config_validation_rejects_invalid_risk_inputs(kwargs, message):
    config = RunConfig(**kwargs)
    with pytest.raises(ValueError, match=message):
        config.validate()
