import json
from pathlib import Path

import pytest

from momentum_factor_lab.config import WEIGHTING_POLICIES
from momentum_factor_lab.workflow import AnalysisResult, result_payload, write_result_json


def test_result_json_persists_schema_v4_joint_grid_and_identity(
    demo_result: AnalysisResult,
) -> None:
    path = write_result_json(demo_result)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.suffix == ".json"
    assert payload["schemaVersion"] == 4
    assert payload["resultKey"] == payload["resultIdentity"]["resultKey"]
    assert len(payload["resultKey"]) == 64
    assert payload["selectedFactor"] == demo_result.selected_factor
    assert payload["selectedWeightingPolicy"] == demo_result.selected_policy
    assert payload["meta"]["factorCount"] == 64
    assert payload["meta"]["independentFactorCount"] == 61
    assert payload["meta"]["aliasFactorCount"] == 3
    assert payload["meta"]["policyCount"] == 4
    assert payload["meta"]["policyFactorRunCount"] == 256
    assert len(payload["meta"]["factorDefinitionSha256"]) == 64
    assert len(payload["meta"]["policyDefinitionSha256"]) == 64
    assert len(payload["meta"]["selectionSpecSha256"]) == 64
    assert len(payload["factorPolicyRanking"]) == 256
    assert "factorRanking" not in payload
    assert "policyFactorMetrics" not in payload
    assert "modelPortfolio" not in payload
    assert set(payload["factorPortfolios"]) == set(demo_result.factor_scores)
    assert payload["data"]["inputSha256"] == demo_result.market_data.input_sha256
    assert payload["data"]["analyzedSymbols"] == demo_result.market_data.candidate_symbols
    assert payload["priceSources"] == demo_result.market_data.price_sources.to_dict(
        orient="records"
    )
    assert payload["sourceHealth"] == demo_result.market_data.data_sources.to_dict(orient="records")
    assert payload["researchScope"]["researchOnly"] is True
    assert payload["researchScope"]["notInvestmentRecommendation"] is True
    assert len(payload["researchScope"]["limitations"]) >= 3
    assert payload["researchInputs"]["evaluationWindowDays"] == 756
    selected = next(row for row in payload["factorPolicyRanking"] if row["selected"])
    assert selected["min_target_effective_names"] <= selected["median_target_effective_names"]
    assert selected["max_target_hhi"] >= selected["median_target_hhi"]
    assert selected["current_target_effective_names"] == pytest.approx(
        payload["currentResearchTarget"]["concentration"]["effectiveNames"]
    )
    assert selected["current_target_hhi"] == pytest.approx(
        payload["currentResearchTarget"]["concentration"]["riskySleeveHhi"]
    )
    assert selected["current_target_max_weight"] == pytest.approx(
        payload["currentResearchTarget"]["concentration"]["maxWeight"]
    )
    assert not list(Path(demo_result.config.output_dir).glob("*.pdf"))
    assert not list(Path(demo_result.config.output_dir).glob("*.xlsx"))


def test_factor_policy_grid_registry_and_accounting_survive_serialization(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    factors = set(payload["factorPortfolios"])
    observed = {(row["policy_id"], row["factor"]) for row in payload["factorPolicyRanking"]}

    assert observed == {
        (policy_id, factor) for policy_id in WEIGHTING_POLICIES for factor in factors
    }
    registry = payload["weightingPolicyRegistry"]
    assert set(registry["policies"]) == set(WEIGHTING_POLICIES)
    assert all(row["implementationId"] for row in registry["policies"].values())
    accounting = payload["gridAccounting"]
    assert accounting["expectedIndependentPairCount"] == 244
    assert accounting["missingIndependentPairCount"] == 0
    assert (
        accounting["availableIndependentPairCount"] + accounting["excludedIndependentPairCount"]
        == accounting["expectedIndependentPairCount"]
    )
    assert payload["portfolioPolicy"]["policyAggregateDiagnostics"]["diagnosticOnly"]
    assert payload["selectionMethod"]["policyAggregatesAreDiagnosticOnly"]
    assert payload["selectionMethod"]["equalWeightIsPeerCandidate"]


def test_selected_factor_policy_current_target_and_performance_reconcile(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    selected_factor = payload["selectedFactor"]
    selected_policy = payload["selectedWeightingPolicy"]
    selected_rows = [row for row in payload["factorPolicyRanking"] if row["selected"]]
    portfolio = payload["currentResearchTarget"]

    assert len(selected_rows) == 1
    ranking = selected_rows[0]
    assert ranking["rank"] == 1
    assert ranking["comparison_status"] == "available"
    assert ranking["selection_eligible"] is True
    assert ranking["factor"] == selected_factor
    assert ranking["policy_id"] == selected_policy
    assert payload["portfolioPolicy"]["selectedPolicyId"] == selected_policy
    assert payload["performance"]["weightingPolicyId"] == selected_policy
    assert portfolio == payload["factorPortfolios"][selected_factor]
    assert portfolio["factor"] == selected_factor
    assert portfolio["weightingPolicyId"] == selected_policy
    assert portfolio["asOf"] == portfolio["signalDate"] == payload["data"]["asOf"]
    assert sum(row["weight"] for row in portfolio["weights"]) + portfolio[
        "cashWeight"
    ] == pytest.approx(1.0)
    assert len({row["symbol"] for row in portfolio["weights"]}) == len(portfolio["weights"])
    assert payload["contributionDiagnostics"]["observedReturnsPreserved"] is True
    assert payload["contributionDiagnostics"]["reoptimized"] is False


def test_current_transition_uses_cash_inclusive_half_l1_and_one_cost_charge(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    held = payload["backtestHeldPortfolio"]
    target = payload["currentResearchTarget"]
    transition = payload["currentTransition"]
    held_weights = {row["symbol"]: row["weight"] for row in held["weights"]}
    target_weights = {row["symbol"]: row["weight"] for row in target["weights"]}
    symbols = set(held_weights) | set(target_weights)
    expected_turnover = 0.5 * (
        sum(
            abs(target_weights.get(symbol, 0.0) - held_weights.get(symbol, 0.0))
            for symbol in symbols
        )
        + abs(target["cashWeight"] - held["cashWeight"])
    )

    assert transition["asOf"] == payload["data"]["asOf"]
    assert transition["targetSignalDate"] == target["signalDate"]
    assert transition["actualNextClosePretradeDriftKnown"] is False
    assert transition["turnoverFormula"] == (
        "0.5*(sum_abs_target_minus_pretrade_stock+abs_target_minus_pretrade_cash)"
    )
    assert transition["costFormula"] == "one_way_turnover*total_cost_bps/10000"
    assert transition["targetCashWeight"] == pytest.approx(target["cashWeight"])
    assert transition["totalCostBps"] == pytest.approx(payload["config"]["total_cost_bps"])
    if transition["valuationAvailable"]:
        assert transition["oneWayTurnover"] == pytest.approx(expected_turnover)
        assert transition["modeledCostFraction"] == pytest.approx(
            expected_turnover * payload["config"]["total_cost_bps"] / 10_000.0
        )
    else:
        assert transition["oneWayTurnover"] is None
        assert transition["modeledCostFraction"] is None


def test_data_mode_and_requested_to_eligible_funnel_are_explicit(
    demo_result: AnalysisResult,
) -> None:
    data = result_payload(demo_result)["data"]
    counts = [
        data["requestedCandidateCount"],
        data["providerReturnedCandidateCount"],
        data["inputSecurityCount"],
        data["analyzedSecurityCount"],
        data["latestEligibleSecurityCount"],
    ]

    assert data["mode"] == "demo"
    assert data["synthetic"] is True
    assert all(isinstance(value, int) and value >= 0 for value in counts)
    assert counts == sorted(counts, reverse=True)
    assert data["inputSecurityCount"] == data["analyzedSecurityCount"] == 50


def test_all_performance_curves_share_the_selected_policy_dates(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    performance = payload["performance"]
    dates = performance["dates"]

    assert performance["weightingPolicyId"] == payload["selectedWeightingPolicy"]
    assert len(dates) == demo_result.config.evaluation_window_days
    assert set(performance["factorCurves"]) == set(demo_result.factor_scores)
    assert all(len(curve) == len(dates) for curve in performance["factorCurves"].values())


def test_payload_is_compact_enough_for_static_web(demo_result: AnalysisResult) -> None:
    encoded = json.dumps(
        result_payload(demo_result),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    assert len(encoded) < 5_000_000
