from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from momentum_factor_lab import workflow as workflow_module
from momentum_factor_lab.advanced_factors import ADVANCED_FACTOR_NAMES, AdvancedFactorResult
from momentum_factor_lab.config import POLICY_REGISTRY, RunConfig, WEIGHTING_POLICIES
from momentum_factor_lab.portfolio import construct_target_allocation
from momentum_factor_lab.workflow import (
    AnalysisResult,
    _apply_joint_guardrails,
    _policy_grid_reasons,
    run_analysis,
)


def test_factor_catalog_and_complete_joint_grid(demo_result: AnalysisResult) -> None:
    definitions = demo_result.factor_definitions.set_index("factor")
    ranking = demo_result.factor_ranking
    aliases = definitions["compatibility_alias_of"].dropna()

    assert len(demo_result.factor_scores) == 64
    assert len(definitions) == 64
    assert int(definitions["selection_eligible"].fillna(True).astype(bool).sum()) == 61
    assert len(aliases) == 3
    assert set(aliases.index) == {
        "acceleration",
        "relative_strength_6m",
        "short_acceleration",
    }
    assert len(ranking) == 64 * len(WEIGHTING_POLICIES) == 256
    assert not ranking.duplicated(["factor", "policy_id"]).any()
    alias_rows = ranking[ranking["factor"].isin(aliases.index)]
    assert alias_rows["comparison_status"].eq("duplicate_alias").all()
    assert alias_rows["comparison_eligible"].eq(False).all()
    assert alias_rows["composite_score"].isna().all()

    accounting = demo_result.grid_accounting
    assert accounting["independentFactorCount"] == 61
    assert accounting["policyCount"] == 4
    assert accounting["expectedIndependentPairCount"] == 244
    assert accounting["evaluatedIndependentPairCount"] == 244
    assert (
        accounting["availableIndependentPairCount"] + accounting["excludedIndependentPairCount"]
        == accounting["expectedIndependentPairCount"]
    )
    assert accounting["missingIndependentPairCount"] == 0
    assert accounting["diagnosticAliasPairCount"] == 12


def test_joint_selection_scores_every_available_pair_once(demo_result: AnalysisResult) -> None:
    ranking = demo_result.factor_ranking
    available = ranking.loc[ranking["comparison_status"].eq("available")]
    selected = ranking.loc[ranking["selected"]]

    assert len(selected) == 1
    assert selected.iloc[0]["factor"] == demo_result.selected_factor
    assert selected.iloc[0]["policy_id"] == demo_result.selected_policy
    assert int(selected.iloc[0]["rank"]) == 1
    assert available["composite_score"].between(0.0, 100.0).all()
    assert available["policy_id"].nunique() == 4
    assert demo_result.factor_selection_decision["method"] == "joint_factor_policy"
    assert demo_result.policy_selection_decision["diagnosticOnly"] is True
    assert demo_result.policy_selection_decision["selectedByPolicyAggregate"] is False

    row = selected.iloc[0]
    expected = sum(
        row[f"{metric}_score"] * weight
        for metric, weight in demo_result.config.score_weights.items()
    )
    assert np.isfinite(expected)
    assert row["base_composite_score"] == pytest.approx(expected)
    assert row["selection_score"] == pytest.approx(
        row["base_composite_score"] - row["extreme_event_penalty_points"]
    )


def test_equal_weight_is_a_peer_not_an_absolute_guardrail_baseline(
    demo_result: AnalysisResult,
) -> None:
    baseline, *_ = _apply_joint_guardrails(
        demo_result.factor_ranking.copy(),
        demo_result.config,
    )
    changed = demo_result.factor_ranking.copy()
    equal = changed["policy_id"].eq("equal_weight")
    changed.loc[equal, "sharpe"] = -9.0
    changed.loc[equal, "max_drawdown"] = -0.99
    changed.loc[equal, "composite_score"] = 0.0
    rescored, *_ = _apply_joint_guardrails(changed, demo_result.config)

    fields = [
        "factor",
        "policy_id",
        "guardrail_sharpe",
        "guardrail_drawdown",
        "standard_guardrail_pass",
    ]
    before = baseline.loc[~baseline["policy_id"].eq("equal_weight"), fields].sort_values(
        ["factor", "policy_id"]
    )
    after = rescored.loc[~rescored["policy_id"].eq("equal_weight"), fields].sort_values(
        ["factor", "policy_id"]
    )
    pd.testing.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True))


def test_joint_selection_can_choose_a_pair_from_any_policy(
    demo_result: AnalysisResult,
) -> None:
    ranking = demo_result.factor_ranking.copy()
    selected_source = ranking.loc[ranking["selected"]].iloc[0]
    candidates = ranking[
        ranking["comparison_status"].eq("available")
        & ~ranking["policy_id"].eq(demo_result.selected_policy)
    ]
    target_index = candidates.index[0]
    target_identity = ranking.loc[target_index, ["factor", "policy_id"]].to_dict()
    metric_columns = [
        "sharpe",
        "max_drawdown",
        "annualized_cost_drag",
        "min_target_effective_names",
        "current_target_effective_names",
        "max_target_hhi",
        "current_target_hhi",
        "max_target_weight",
        "current_target_max_weight",
        "policy_input_coverage_ratio",
        "execution_coverage_ratio",
        "blocked_execution_count",
        "total_unpriceable_target_count",
        "current_portfolio_available",
        "contribution_diagnostics_complete",
        "max_abs_security_day_contribution",
        "max_security_absolute_contribution_share",
        "max_abs_leave_one_security_cagr_delta",
    ]
    ranking.loc[:, "composite_score"] = 1.0
    ranking.loc[target_index, metric_columns] = selected_source[metric_columns].to_numpy()
    ranking.loc[target_index, "composite_score"] = 100.0

    _, selected_factor, selected_policy, _, decision = _apply_joint_guardrails(
        ranking,
        demo_result.config,
    )
    assert selected_factor == target_identity["factor"]
    assert selected_policy == target_identity["policy_id"]
    assert decision["selectedFactor"] == target_identity["factor"]
    assert decision["selectedPolicyId"] == target_identity["policy_id"]


def test_absolute_concentration_guardrails_use_historical_worst_case_and_current_target(
    demo_result: AnalysisResult,
) -> None:
    ranking = demo_result.factor_ranking.copy()
    source = ranking.loc[ranking["selected"]].iloc[0]
    identity = (str(source["factor"]), str(source["policy_id"]))
    mask = ranking["factor"].eq(identity[0]) & ranking["policy_id"].eq(identity[1])
    boundary_values = {
        "min_target_effective_names": demo_result.config.selection_min_effective_names,
        "current_target_effective_names": demo_result.config.selection_min_effective_names,
        "max_target_hhi": demo_result.config.selection_max_target_hhi,
        "current_target_hhi": demo_result.config.selection_max_target_hhi,
        "max_target_weight": demo_result.config.selection_max_target_weight,
        "current_target_max_weight": demo_result.config.selection_max_target_weight,
    }
    for field, value in boundary_values.items():
        ranking.loc[mask, field] = value

    boundary, *_ = _apply_joint_guardrails(ranking, demo_result.config)
    boundary_row = boundary.loc[
        boundary["factor"].eq(identity[0]) & boundary["policy_id"].eq(identity[1])
    ].iloc[0]
    for field in (
        "guardrail_historical_effective_names",
        "guardrail_current_effective_names",
        "guardrail_historical_target_hhi",
        "guardrail_current_target_hhi",
        "guardrail_historical_target_weight",
        "guardrail_current_target_weight",
    ):
        assert bool(boundary_row[field])

    failures = {
        "min_target_effective_names": (
            demo_result.config.selection_min_effective_names - 0.01,
            "guardrail_historical_effective_names",
        ),
        "current_target_effective_names": (
            demo_result.config.selection_min_effective_names - 0.01,
            "guardrail_current_effective_names",
        ),
        "max_target_hhi": (
            demo_result.config.selection_max_target_hhi + 0.01,
            "guardrail_historical_target_hhi",
        ),
        "current_target_hhi": (
            demo_result.config.selection_max_target_hhi + 0.01,
            "guardrail_current_target_hhi",
        ),
        "max_target_weight": (
            demo_result.config.selection_max_target_weight + 0.01,
            "guardrail_historical_target_weight",
        ),
        "current_target_max_weight": (
            demo_result.config.selection_max_target_weight + 0.01,
            "guardrail_current_target_weight",
        ),
    }
    for metric, (value, guardrail) in failures.items():
        changed = ranking.copy()
        changed.loc[mask, metric] = value
        guarded, *_ = _apply_joint_guardrails(changed, demo_result.config)
        row = guarded.loc[
            guarded["factor"].eq(identity[0]) & guarded["policy_id"].eq(identity[1])
        ].iloc[0]
        assert not bool(row[guardrail])
        assert not bool(row["selection_eligible"])
        assert row["selection_status"] == "absolute_guardrail_excluded"


@pytest.mark.parametrize(
    ("action", "expected_status", "expected_eligible", "expected_penalty"),
    [
        ("warn", "extreme_event_warning", True, 0.0),
        ("penalize", "extreme_event_penalized", True, 20.0),
        ("exclude", "extreme_event_excluded", False, 0.0),
    ],
)
def test_extreme_event_actions_apply_the_same_absolute_threshold(
    demo_result: AnalysisResult,
    action: str,
    expected_status: str,
    expected_eligible: bool,
    expected_penalty: float,
) -> None:
    ranking = demo_result.factor_ranking.copy()
    source = ranking.loc[ranking["selected"]].iloc[0]
    identity = (str(source["factor"]), str(source["policy_id"]))
    observed = float(source["max_abs_security_day_contribution"])
    assert observed > 0.0
    threshold = observed / 2.0
    ranking["max_abs_security_day_contribution"] = threshold
    ranking.loc[
        ranking["factor"].eq(identity[0]) & ranking["policy_id"].eq(identity[1]),
        "max_abs_security_day_contribution",
    ] = observed
    config = replace(
        demo_result.config,
        selection_max_abs_security_day_contribution=threshold,
        selection_extreme_event_action=action,
        selection_extreme_event_penalty_points=20.0,
    )

    guarded, *_ = _apply_joint_guardrails(ranking, config)
    row = guarded.loc[
        guarded["factor"].eq(identity[0]) & guarded["policy_id"].eq(identity[1])
    ].iloc[0]

    assert row["selection_status"] == expected_status
    assert bool(row["selection_eligible"]) is expected_eligible
    assert row["extreme_event_penalty_points"] == pytest.approx(expected_penalty)
    assert row["contribution_guardrail_breaches"] == ["security_day_contribution"]


def test_extreme_event_threshold_boundary_passes_without_warning(
    demo_result: AnalysisResult,
) -> None:
    ranking = demo_result.factor_ranking.copy()
    source = ranking.loc[ranking["selected"]].iloc[0]
    identity = (str(source["factor"]), str(source["policy_id"]))
    config = replace(
        demo_result.config,
        selection_max_abs_security_day_contribution=float(
            source["max_abs_security_day_contribution"]
        ),
        selection_extreme_event_action="exclude",
    )

    guarded, *_ = _apply_joint_guardrails(ranking, config)
    row = guarded.loc[
        guarded["factor"].eq(identity[0]) & guarded["policy_id"].eq(identity[1])
    ].iloc[0]

    assert bool(row["guardrail_security_day_contribution"])
    assert "security_day_contribution" not in row["contribution_guardrail_breaches"]


def test_missing_factor_policy_pair_is_an_implementation_error(
    demo_result: AnalysisResult,
) -> None:
    all_backtests = {policy: dict(demo_result.backtests) for policy in WEIGHTING_POLICIES}
    missing_factor = next(iter(demo_result.backtests))
    del all_backtests[WEIGHTING_POLICIES[-1]][missing_factor]
    evaluation_index = pd.DatetimeIndex(
        demo_result.backtests[missing_factor].returns.index[
            -demo_result.config.evaluation_window_days :
        ]
    )
    with pytest.raises(ValueError, match="implementation_error_missing_factor_policy_pairs"):
        _policy_grid_reasons(
            all_backtests,
            evaluation_index,
            expected_factors=demo_result.backtests,
        )


def test_unknown_or_internal_policy_input_reason_is_an_implementation_error() -> None:
    dates = pd.bdate_range("2026-01-02", periods=3)
    all_backtests: dict[str, dict[str, SimpleNamespace]] = {}
    for policy in WEIGHTING_POLICIES:
        statuses = pd.Series(["not_scheduled", "available", "not_scheduled"], index=dates)
        reasons = pd.Series([(), (), ()], index=dates)
        if policy == "capped_vol_adjusted_rank":
            statuses.iloc[1] = "unavailable"
            reasons.iloc[1] = ("weight_invariant_failed",)
        all_backtests[policy] = {
            "factor_x": SimpleNamespace(
                policy_input_statuses=statuses,
                policy_input_reasons=reasons,
            )
        }

    with pytest.raises(ValueError, match="implementation_error_policy_input_reason"):
        _policy_grid_reasons(all_backtests, dates, expected_factors=["factor_x"])


def test_legitimate_policy_input_shortage_preserves_policy_reason_and_date() -> None:
    dates = pd.bdate_range("2026-01-02", periods=3)
    all_backtests: dict[str, dict[str, SimpleNamespace]] = {}
    for policy in WEIGHTING_POLICIES:
        statuses = pd.Series(["not_scheduled", "available", "not_scheduled"], index=dates)
        reasons = pd.Series([(), (), ()], index=dates)
        if policy == "capped_vol_adjusted_rank":
            statuses.iloc[1] = "unavailable"
            reasons.iloc[1] = ("no_finite_trailing_volatility",)
        all_backtests[policy] = {
            "factor_x": SimpleNamespace(
                policy_input_statuses=statuses,
                policy_input_reasons=reasons,
            )
        }

    issue = _policy_grid_reasons(
        all_backtests,
        dates,
        expected_factors=["factor_x"],
    )["factor_x"]

    assert issue is not None
    assert issue["detail"] == "successful_rebalance_dates_differ"
    assert issue["policyFailures"] == [
        {
            "policyId": "capped_vol_adjusted_rank",
            "date": dates[1].date().isoformat(),
            "reasons": ["no_finite_trailing_volatility"],
        }
    ]


def test_policy_diagnostics_do_not_select_a_policy(demo_result: AnalysisResult) -> None:
    diagnostics = demo_result.policy_comparison
    assert len(diagnostics) == 4
    assert set(diagnostics["policy_id"]) == set(WEIGHTING_POLICIES)
    assert diagnostics["diagnostic_only"].eq(True).all()
    assert "selected" not in diagnostics
    assert "rank" not in diagnostics


def test_weighting_policy_registry_is_explicit_and_versioned() -> None:
    assert set(POLICY_REGISTRY) == set(WEIGHTING_POLICIES)
    assert len({row["implementationId"] for row in POLICY_REGISTRY.values()}) == 4
    assert all(row["requiredSignalDateInputs"] for row in POLICY_REGISTRY.values())
    assert all(row["formula"] for row in POLICY_REGISTRY.values())
    liquidity = POLICY_REGISTRY["score_liquidity_rank"]
    assert "market_cap" not in liquidity["formula"]
    assert "liquidity" in liquidity["implementationId"]


@pytest.mark.parametrize(
    ("policy_id", "reason"),
    [
        ("capped_vol_adjusted_rank", "no_finite_trailing_volatility"),
        ("score_liquidity_rank", "no_finite_trailing_dollar_volume"),
    ],
)
def test_policy_with_missing_required_input_fails_closed_to_cash(
    policy_id: str,
    reason: str,
) -> None:
    symbols = pd.Index(["AAA", "BBB", "CCC"])
    allocation = construct_target_allocation(
        policy_id,
        pd.Timestamp("2026-07-10"),
        pd.Series([3.0, 2.0, 1.0], index=symbols),
        pd.Series([30.0, 20.0, 10.0], index=symbols),
        pd.Series(True, index=symbols),
        RunConfig(demo=True, top_n=3, max_weight=0.50),
    )

    assert allocation.status == "unavailable"
    assert allocation.reasons == [reason]
    assert allocation.rows.empty
    assert allocation.cash_weight == pytest.approx(1.0)


def test_joint_selection_fails_closed_when_every_pair_breaks_guardrails(
    demo_result: AnalysisResult,
) -> None:
    ranking = demo_result.factor_ranking.copy()
    ranking["execution_coverage_ratio"] = 0.0
    ranking["blocked_execution_count"] = 1
    ranking["total_unpriceable_target_count"] = 1
    with pytest.raises(ValueError, match="no factor-policy pair passes"):
        _apply_joint_guardrails(ranking, demo_result.config)


def test_unavailable_advanced_factors_remain_in_the_canonical_four_policy_grid(
    demo_result: AnalysisResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = workflow_module.compute_advanced_factor_scores

    def force_both_advanced_factors_unavailable(*args, **kwargs) -> AdvancedFactorResult:
        computed = original(*args, **kwargs)
        scores = {factor: panel.copy() for factor, panel in computed.scores.items()}
        status = computed.status.copy()
        for factor in ADVANCED_FACTOR_NAMES:
            scores[factor].iloc[-1, :] = np.nan
            mask = status["factor"].eq(factor)
            status.loc[mask, "available"] = False
            status.loc[mask, "latestFiniteCount"] = 0
            status.loc[mask, "reasonCode"] = "forced_distinct_advanced_input_shortage"
            status.loc[mask, "detail"] = f"forced unavailable fixture for {factor}"
        return AdvancedFactorResult(scores=scores, status=status)

    monkeypatch.setattr(
        workflow_module,
        "compute_advanced_factor_scores",
        force_both_advanced_factors_unavailable,
    )
    result = run_analysis(demo_result.config, market_data=demo_result.market_data)
    rows = result.factor_ranking[result.factor_ranking["factor"].isin(ADVANCED_FACTOR_NAMES)]

    assert len(result.factor_scores) == 64
    assert len(result.factor_ranking) == 256
    assert result.grid_accounting["expectedIndependentPairCount"] == 244
    assert result.grid_accounting["missingIndependentPairCount"] == 0
    assert len(rows) == len(ADVANCED_FACTOR_NAMES) * len(WEIGHTING_POLICIES) == 8
    assert rows["comparison_status"].eq("factor_input_unavailable").all()
    assert rows["comparison_eligible"].eq(False).all()
    assert (
        rows["exclusion_reason_codes"]
        .map(lambda codes: list(codes) == ["factor_input_unavailable"])
        .all()
    )
    assert set(rows["factor"]) == set(ADVANCED_FACTOR_NAMES)
    assert result.grid_accounting["exclusionReasonCounts"]["factor_input_unavailable"] == 8
