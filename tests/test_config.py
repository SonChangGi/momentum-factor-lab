import pytest

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.universe import load_packaged_universe_frame


def test_config_defaults_to_top_20_and_large_stock_only_universe():
    config = RunConfig()
    packaged = load_packaged_universe_frame()
    assert config.top_n == 20
    assert config.universe_profile == "large_liquid"
    assert config.factor_selection_mode == "research_validation"
    assert config.effective_factor_selection_mode == "research_validation"
    assert len(config.universe) >= 2000
    assert len(packaged) >= 2000
    assert not packaged["is_etf"].any()


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
        ({"selected_factor": ""}, "selected_factor"),
        ({"target_aum": 0}, "target_aum"),
        ({"max_adv_participation": 0}, "max_adv_participation"),
        ({"max_adv_participation": 1.1}, "max_adv_participation"),
        ({"point_in_time_universe_provenance": ""}, "point_in_time_universe_provenance"),
        ({"min_tradable_universe_size": 0}, "min_tradable_universe_size"),
        ({"min_liquidity_observations": 0}, "min_liquidity_observations"),
        ({"universe_profile": "all_assets"}, "universe_profile"),
        ({"factor_selection_mode": "best_live"}, "factor_selection_mode"),
        ({"selection_window": ""}, "selection_window"),
        ({"cost_stress_high_bps": -1}, "cost_stress_high_bps"),
        ({"sec_user_agent": ""}, "sec_user_agent"),
    ],
)
def test_config_validation_rejects_invalid_risk_inputs(kwargs, message):
    config = RunConfig(**kwargs)
    with pytest.raises(ValueError, match=message):
        config.validate()


def test_selected_factor_defaults_to_predeclared_effective_mode():
    config = RunConfig(selected_factor="mom_1m")

    assert config.factor_selection_mode == "research_validation"
    assert config.effective_factor_selection_mode == "predeclared"


def test_aggressive_profile_lowers_discovery_threshold_only():
    config = RunConfig(universe_profile="aggressive_stock_only", min_avg_dollar_volume=5_000_000)

    assert config.discovery_min_avg_dollar_volume == 1_000_000
    assert config.min_avg_dollar_volume == 5_000_000
