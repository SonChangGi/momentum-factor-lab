import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from momentum_factor_lab.config import POLICY_REGISTRY, WEIGHTING_POLICIES
from momentum_factor_lab.dashboard import (
    WEB_ROOT,
    _factor_sets,
    _load_payload,
    _validate_data,
    write_dashboard_site,
)
from momentum_factor_lab.data import canonical_records_sha256
from momentum_factor_lab.identity import canonical_json_bytes
from momentum_factor_lab.workflow import AnalysisResult, result_payload


Payload = dict[str, Any]
PayloadMutation = Callable[[Payload], None]


def _selected_row(payload: Payload) -> dict[str, Any]:
    return next(row for row in payload["factorPolicyRanking"] if row["selected"] is True)


def _alter_result_key(payload: Payload) -> None:
    result_key = str(payload["resultKey"])
    payload["resultKey"] = ("0" if result_key[0] != "0" else "1") + result_key[1:]


def _append_duplicate_grid_pair(payload: Payload) -> None:
    payload["factorPolicyRanking"].append(deepcopy(payload["factorPolicyRanking"][0]))


def _remove_grid_pair(payload: Payload) -> None:
    payload["factorPolicyRanking"].pop()


def _alter_grid_accounting(payload: Payload) -> None:
    payload["gridAccounting"]["evaluatedIndependentPairCount"] -= 1


def _alter_selected_factor(payload: Payload) -> None:
    selected = str(payload["selectedFactor"])
    payload["selectedFactor"] = next(
        row["factor"]
        for row in payload["factorPolicyRanking"]
        if row["factor"] != selected and row["comparison_status"] == "available"
    )


def _alter_selected_policy(payload: Payload) -> None:
    selected = str(payload["selectedWeightingPolicy"])
    payload["selectedWeightingPolicy"] = next(
        policy for policy in WEIGHTING_POLICIES if policy != selected
    )


def _alter_selected_guardrail(payload: Payload) -> None:
    row = _selected_row(payload)
    row["guardrail_sharpe"] = not row["guardrail_sharpe"]


def _alter_selected_score(payload: Payload) -> None:
    _selected_row(payload)["selection_score"] += 0.25


def _alter_selected_rank(payload: Payload) -> None:
    _selected_row(payload)["rank"] = 2.0


def _alter_selected_flag(payload: Payload) -> None:
    _selected_row(payload)["selected"] = False


def _alter_decision_identity(payload: Payload) -> None:
    selected = str(payload["selectionDecision"]["selectedPolicyId"])
    payload["selectionDecision"]["selectedPolicyId"] = next(
        policy for policy in WEIGHTING_POLICIES if policy != selected
    )


def _alter_guardrail_profile(payload: Payload) -> None:
    payload["selectionDecision"]["guardrailProfile"]["policyNeutral"] = False


def _alter_policy_diagnostic(payload: Payload) -> None:
    payload["policyDiagnostics"][0]["sharpe"] += 1.0


def _alter_registry(payload: Payload) -> None:
    first_policy = WEIGHTING_POLICIES[0]
    payload["weightingPolicyRegistry"]["policies"][first_policy]["formula"] = "tampered"


def _alter_research_inputs(payload: Payload) -> None:
    payload["researchInputs"]["topN"] += 1


def _alter_current_raw_score(payload: Payload) -> None:
    payload["currentResearchTarget"]["weights"][0]["rawPolicyScore"] += 0.125


def _alter_current_weight(payload: Payload) -> None:
    payload["currentResearchTarget"]["weights"][0]["weight"] += 0.01


def _alter_current_concentration(payload: Payload) -> None:
    payload["currentResearchTarget"]["concentration"]["effectiveNames"] += 1.0


def _alter_selected_current_guardrail_input(payload: Payload) -> None:
    _selected_row(payload)["current_target_effective_names"] += 0.25


def _alter_held_weight(payload: Payload) -> None:
    payload["backtestHeldPortfolio"]["weights"][0]["weight"] += 0.01


def _alter_transition_cost(payload: Payload) -> None:
    payload["currentTransition"]["modeledCostFraction"] += 0.01


def _alter_contribution_event(payload: Payload) -> None:
    event = payload["contributionDiagnostics"]["maxExactSingleSessionSecurityContribution"]
    event["absoluteContribution"] += 0.01


def _alter_contribution_cross_field(payload: Payload) -> None:
    _selected_row(payload)["max_abs_security_observation_contribution"] += 0.01


def _add_legacy_alias(payload: Payload) -> None:
    payload["factorRanking"] = []


def _alter_funnel(payload: Payload) -> None:
    payload["data"]["funnel"]["analyzedSecurityCount"] -= 1


def test_dashboard_accepts_schema_v4_joint_result(demo_result: AnalysisResult) -> None:
    payload = result_payload(demo_result)

    loaded = _load_payload(payload)
    selected = _selected_row(loaded)

    assert loaded is payload
    assert loaded["schemaVersion"] == 4
    assert selected["factor"] == loaded["selectedFactor"]
    assert selected["policy_id"] == loaded["selectedWeightingPolicy"]
    assert selected["rank"] == 1.0
    assert loaded["selectionDecision"]["guardrailProfile"]["policyNeutral"] is True
    assert "equalWeightBaseline" not in loaded["selectionDecision"]["guardrailProfile"]


def test_dashboard_live_data_requires_hashed_provider_provenance() -> None:
    price_sources = [
        {"symbol": f"SYM{index:04d}", "price_source": "actual-provider-fixture"}
        for index in range(2_700)
    ]
    source_health = [{"source": "actual-provider-fixture", "status": "ok"}]
    payload = {
        "config": {"data_mode": "live_market"},
        "priceSources": price_sources,
        "sourceHealth": source_health,
        "data": {
            "mode": "live_market",
            "synthetic": False,
            "asOf": "2026-07-10",
            "startDate": "2020-01-02",
            "observations": 1_640,
            "requestedCandidateCount": 2_865,
            "providerReturnedCandidateCount": 2_861,
            "inputSecurityCount": 2_700,
            "analyzedSecurityCount": 2_700,
            "latestEligibleSecurityCount": 2_200,
            "funnel": {
                "label": "canonical_analysis_funnel",
                "authoritative": True,
                "requestedCandidateCount": 2_865,
                "providerUsableCandidateCount": 2_861,
                "analyzedSecurityCount": 2_700,
                "latestEligibleSecurityCount": 2_200,
            },
            "rawCloseAvailable": True,
            "snapshotReadContract": {"pandasFloatPrecision": "round_trip"},
            "inputSha256": {
                "prices": "8" * 64,
                "volumes": "9" * 64,
                "dollarVolumes": "0" * 64,
                "rawCloses": "a" * 64,
                "requestedSymbols": "b" * 64,
                "returnedSymbols": "c" * 64,
                "universeRecords": "d" * 64,
                "priceSources": canonical_records_sha256(price_sources),
                "dataSources": canonical_records_sha256(source_health),
            },
            "analyzedSymbols": [row["symbol"] for row in price_sources],
        },
    }

    assert _validate_data(payload) == "2026-07-10"

    payload["priceSources"][0]["price_source"] = "silently-mutated-provider"
    with pytest.raises(ValueError, match="provenance hashes"):
        _validate_data(payload)


def test_dashboard_accepts_and_verifies_static_grid_identity_transport(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    identity = payload["resultIdentity"]
    identity["canonicalKeyPartsJson"] = canonical_json_bytes(identity["keyParts"]).decode("utf-8")

    assert _load_payload(payload) is payload

    payload["resultIdentity"]["canonicalKeyPartsJson"] = (
        f" {payload['resultIdentity']['canonicalKeyPartsJson']} "
    )
    with pytest.raises(ValueError, match="canonical transport"):
        _load_payload(payload)


def test_dashboard_validates_complete_unique_factor_policy_grid(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    grid = payload["gridAccounting"]
    pairs = {(row["factor"], row["policy_id"]) for row in payload["factorPolicyRanking"]}

    assert len(pairs) == len(payload["factorPolicyRanking"])
    assert grid["policyCount"] == len(WEIGHTING_POLICIES)
    assert grid["evaluatedIndependentPairCount"] == grid["expectedIndependentPairCount"]
    assert (
        grid["availableIndependentPairCount"] + grid["excludedIndependentPairCount"]
        == grid["expectedIndependentPairCount"]
    )


def test_dashboard_requires_the_exact_canonical_factor_registry(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    payload["factorDefinitions"] = payload["factorDefinitions"][:-1]

    with pytest.raises(ValueError, match="canonical 64/61/3 registry"):
        _factor_sets(payload)


def test_dashboard_guardrail_profile_names_historical_worst_case_and_current_metrics(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    rules = payload["selectionDecision"]["guardrailProfile"]["rules"]
    metrics = {rule["metric"] for rule in rules}

    assert {
        "min_target_effective_names",
        "current_target_effective_names",
        "max_target_hhi",
        "current_target_hhi",
        "max_target_weight",
        "current_target_max_weight",
    }.issubset(metrics)
    assert "median_target_effective_names" not in metrics
    assert "median_target_hhi" not in metrics


def test_dashboard_policy_registry_is_canonical_and_policy_neutral(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    registry = payload["weightingPolicyRegistry"]["policies"]

    assert registry == POLICY_REGISTRY
    assert tuple(registry) == WEIGHTING_POLICIES
    assert registry["score_liquidity_rank"]["requiredSignalDateInputs"] == [
        "factor_score",
        "eligible_adjusted_close",
        "trailing_raw_close_times_raw_volume",
    ]
    assert all("market_cap" not in definition["formula"] for definition in registry.values())


@pytest.mark.parametrize(
    "mutate",
    [
        _alter_result_key,
        _append_duplicate_grid_pair,
        _remove_grid_pair,
        _alter_grid_accounting,
        _alter_selected_factor,
        _alter_selected_policy,
        _alter_selected_guardrail,
        _alter_selected_score,
        _alter_selected_rank,
        _alter_selected_flag,
        _alter_decision_identity,
        _alter_guardrail_profile,
        _alter_policy_diagnostic,
        _alter_registry,
        _alter_research_inputs,
        _alter_current_raw_score,
        _alter_current_weight,
        _alter_current_concentration,
        _alter_selected_current_guardrail_input,
        _alter_held_weight,
        _alter_transition_cost,
        _alter_contribution_event,
        _alter_contribution_cross_field,
        _add_legacy_alias,
        _alter_funnel,
    ],
    ids=lambda mutate: mutate.__name__,
)
def test_dashboard_rejects_mutated_canonical_contracts(
    demo_result: AnalysisResult,
    mutate: PayloadMutation,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    mutate(payload)

    with pytest.raises(ValueError):
        _load_payload(payload)


def test_dashboard_summary_preserves_identity_and_selected_allocation_exactly(
    demo_result: AnalysisResult,
    tmp_path: Path,
) -> None:
    paths = write_dashboard_site(demo_result, tmp_path / "site")
    payload = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
    data = payload["data"]

    assert summary["schemaVersion"] == payload["schemaVersion"] == 4
    assert summary["contract"] == "quant-research-summary"
    assert summary["contractVersion"] == 3
    assert summary["resultKey"] == payload["resultKey"]
    assert summary["resultIdentity"] == payload["resultIdentity"]
    assert summary["dataAsOf"] == data["asOf"]
    assert summary["dataMode"] == data["mode"]
    assert summary["synthetic"] is data["synthetic"]
    assert summary["analyzedSecurityCount"] == data["analyzedSecurityCount"]
    assert summary["selectedFactor"] == payload["selectedFactor"]
    assert summary["selectedWeightingPolicy"] == payload["selectedWeightingPolicy"]
    assert summary["currentResearchTarget"] == payload["currentResearchTarget"]
    assert summary["weights"] == payload["currentResearchTarget"]["weights"]
    assert summary["cashWeight"] == payload["currentResearchTarget"]["cashWeight"]
    assert summary["contributionDiagnostics"] == payload["contributionDiagnostics"]
    assert summary["gridAccounting"] == payload["gridAccounting"]


def test_dashboard_path_input_and_static_asset_copying_are_preserved(
    demo_result: AnalysisResult,
    tmp_path: Path,
) -> None:
    payload = result_payload(demo_result)
    source_path = tmp_path / "result.json"
    source_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    paths = write_dashboard_site(source_path, tmp_path / "site", title="Joint Grid Test")
    written = json.loads(Path(paths["data"]).read_text(encoding="utf-8"))
    index = Path(paths["index"]).read_text(encoding="utf-8")

    assert written == payload
    assert "Joint Grid Test" in index
    assert "__TITLE__" not in index
    assert "__ASSET_VERSION__" not in index
    assert Path(paths["css"]).read_bytes() == (WEB_ROOT / "styles.css").read_bytes()
    assert Path(paths["js"]).read_bytes() == (WEB_ROOT / "dashboard.js").read_bytes()


def test_dashboard_compact_payload_remains_under_public_limit(
    demo_result: AnalysisResult,
    tmp_path: Path,
) -> None:
    paths = write_dashboard_site(result_payload(demo_result), tmp_path / "site")

    assert Path(paths["data"]).stat().st_size < 5_000_000


def test_dashboard_rejects_schema_v3_and_compatibility_only_input(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    payload["schemaVersion"] = 3
    payload["factorRanking"] = payload.pop("factorPolicyRanking")

    with pytest.raises(ValueError, match="schemaVersion 4"):
        _load_payload(payload)
