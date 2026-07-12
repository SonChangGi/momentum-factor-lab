from pathlib import Path

import pytest

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.research_inputs import (
    RESEARCH_INPUTS_VERSION,
    ResearchInputError,
    ResearchInputs,
)


def test_public_inputs_round_trip_and_apply_to_run_config(tmp_path: Path) -> None:
    inputs = ResearchInputs.from_mapping(
        {
            "version": RESEARCH_INPUTS_VERSION,
            "rebalanceFrequency": "W",
            "evaluationYears": 5,
            "topN": 30,
            "maxWeight": 0.08,
            "transactionCostBps": 7.0,
            "slippageBps": 9.0,
            "minPrice": 10.0,
            "minAvgDollarVolume": 5_000_000.0,
        }
    )
    config = inputs.apply(
        RunConfig(
            demo=True,
            output_dir=tmp_path / "output",
            site_dir=tmp_path / "site",
            cache_dir=tmp_path / "cache",
        )
    )
    assert config.rebalance_frequency == "W"
    assert config.evaluation_window_days == 5 * 252
    assert config.min_evaluation_observations == 4 * 252
    assert config.min_daily_risk_observations == 4 * 252
    assert config.top_n == 30
    assert config.selection_extreme_event_action == "exclude"
    assert config.selection_max_abs_security_day_contribution == pytest.approx(0.25)
    assert ResearchInputs.from_config(config) == inputs
    assert inputs.to_dict()["evaluationWindowDays"] == 1_260
    assert len(inputs.state_key) == 64


@pytest.mark.parametrize(
    "value",
    [
        {"nearestPreset": True},
        {"version": "research-inputs-v0"},
        {"evaluationYears": 0},
        {"evaluationYears": 2.5},
        {"topN": 0},
        {"maxWeight": 0.0},
        {"minLiquidityObservations": 64, "liquidityLookbackDays": 63},
        {"selectionMinEffectiveNames": 21, "topN": 20},
        {"selectionMaxTargetHhi": 0.0},
        {"selectionMaxSecurityAbsoluteContributionShare": 1.01},
        {"selectionExtremeEventAction": "delete_observation"},
    ],
)
def test_invalid_or_unknown_public_inputs_fail_closed(value: dict[str, object]) -> None:
    with pytest.raises(ResearchInputError):
        ResearchInputs.from_mapping(value)


def test_different_public_inputs_have_different_state_keys() -> None:
    baseline = ResearchInputs()
    changed = ResearchInputs(top_n=25)
    assert baseline.state_key != changed.state_key


_NUMERIC_PUBLIC_INPUTS = (
    "evaluationYears",
    "topN",
    "maxWeight",
    "transactionCostBps",
    "slippageBps",
    "minHistoryDays",
    "minPrice",
    "minAvgDollarVolume",
    "minAvgVolume",
    "liquidityLookbackDays",
    "minLiquidityObservations",
    "maxPriceMissingRatio",
    "maxVolumeMissingRatio",
    "maxExtremeDailyReturn",
    "selectionMinSharpe",
    "selectionMaxDrawdown",
    "selectionMaxAnnualizedCostDrag",
    "selectionMinEffectiveNames",
    "selectionMaxTargetHhi",
    "selectionMaxTargetWeight",
    "selectionMaxAbsSecurityDayContribution",
    "selectionMaxSecurityAbsoluteContributionShare",
    "selectionMaxLeaveOneSecurityCagrDelta",
    "selectionExtremeEventPenaltyPoints",
)


@pytest.mark.parametrize("field", _NUMERIC_PUBLIC_INPUTS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_every_numeric_public_input_rejects_nonfinite_values(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ResearchInputError, match="finite number"):
        ResearchInputs.from_mapping({field: value})
