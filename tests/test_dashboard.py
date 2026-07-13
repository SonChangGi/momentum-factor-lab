import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from momentum_factor_lab.config import POLICY_REGISTRY, WEIGHTING_POLICIES
from momentum_factor_lab.dashboard import (
    MAX_DASHBOARD_BYTES,
    WEB_ROOT,
    _factor_sets,
    _load_payload,
    _validate_data,
    externalize_factor_holding_history_sidecar,
    validate_factor_holding_history_sidecar_bytes,
    write_dashboard_site,
)
from momentum_factor_lab.data import canonical_records_sha256
from momentum_factor_lab.identity import canonical_json_bytes
from momentum_factor_lab.workflow import (
    MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES,
    AnalysisResult,
    result_payload,
)


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


def _nonselected_factor_portfolio(payload: Payload) -> dict[str, Any]:
    selected = str(payload["selectedFactor"])
    factor = next(factor for factor in sorted(payload["factorPortfolios"]) if factor != selected)
    return payload["factorPortfolios"][factor]


def _remove_factor_portfolio(payload: Payload) -> None:
    selected = str(payload["selectedFactor"])
    factor = next(factor for factor in sorted(payload["factorPortfolios"]) if factor != selected)
    payload["factorPortfolios"].pop(factor)


def _alter_factor_portfolio_identity(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["factor"] = "tampered_factor"


def _alter_factor_portfolio_policy_version(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["weightingPolicyVersion"] = "tampered-version"


def _alter_factor_portfolio_date(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["signalDate"] = "2026-01-01"


def _alter_factor_portfolio_status(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["status"] = "unavailable"


def _alter_factor_portfolio_count(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["selectedSecurityCount"] += 1


def _alter_factor_portfolio_selection_fraction(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["selectionFraction"] += 0.01


def _alter_factor_portfolio_weight(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["weights"][0]["weight"] += 0.01


def _alter_factor_portfolio_max_weight(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["weights"][0]["maxWeight"] += 0.01


def _alter_factor_portfolio_cash(payload: Payload) -> None:
    _nonselected_factor_portfolio(payload)["cashWeight"] += 0.01


def _forge_unavailable_factor_portfolio_without_reason(payload: Payload) -> None:
    portfolio = _nonselected_factor_portfolio(payload)
    portfolio.update(
        {
            "status": "unavailable",
            "selectedSecurityCount": 0,
            "cashWeight": 1.0,
            "reasons": [],
            "componentStatus": {},
            "weights": [],
            "selectionFraction": 0.0,
            "concentration": {
                "investedWeight": 0.0,
                "cashWeight": 1.0,
                "riskySleeveHhi": 0.0,
                "effectiveNames": 0.0,
                "top1Weight": 0.0,
                "top5Weight": 0.0,
                "maxWeight": 0.0,
            },
        }
    )


def _alter_nonselected_static_grid_portfolio_count(payload: Payload) -> None:
    portfolio = _nonselected_factor_portfolio(payload)
    row = next(
        row
        for row in payload["factorPolicyRanking"]
        if row["factor"] == portfolio["factor"]
        and row["policy_id"] == payload["selectedWeightingPolicy"]
    )
    row["current_holding_count"] += 1


def _alter_selected_portfolio_deep_parity(payload: Payload) -> None:
    payload["currentResearchTarget"]["reasons"].append(
        "top_n_boundary_tie_resolved_by_trailing_dollar_volume"
    )


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


def _alter_holding_history_weight_timing(payload: Payload) -> None:
    payload["selectedBacktestHoldingHistory"]["weightTiming"] = "start_of_session"


def _remove_holding_history_session(payload: Payload) -> None:
    payload["selectedBacktestHoldingHistory"]["sessions"].pop(0)


def _alter_holding_history_final_weight(payload: Payload) -> None:
    payload["selectedBacktestHoldingHistory"]["sessions"][-1]["weights"][0]["weight"] += 0.01


def _alter_holding_history_execution_metadata(payload: Payload) -> None:
    sessions = payload["selectedBacktestHoldingHistory"]["sessions"]
    sessions[-1]["lastExecutionDate"] = sessions[-1]["date"]


def _alter_sidecar_factor_policy(payload: Payload) -> None:
    sidecar = payload["factorHoldingHistorySidecar"]["data"]
    factor = next(iter(sidecar["factors"]))
    sidecar["factors"][factor]["weightingPolicyId"] = "tampered-policy"


def _alter_sidecar_factor_result_key(payload: Payload) -> None:
    sidecar = payload["factorHoldingHistorySidecar"]["data"]
    factor = next(iter(sidecar["factors"]))
    sidecar["factors"][factor]["resultKey"] = "0" * 64


def _alter_sidecar_common_dates(payload: Payload) -> None:
    payload["factorHoldingHistorySidecar"]["data"]["dates"][0] = "2026-01-01"


def _replace_holding_history_session_with_weekend(payload: Payload) -> None:
    history = payload["selectedBacktestHoldingHistory"]
    for index, session in enumerate(history["sessions"][:-1]):
        session_date = date.fromisoformat(session["date"])
        if session_date.weekday() == 4 and session["executionStatus"] == "none":
            session["date"] = (session_date + timedelta(days=1)).isoformat()
            if index == 0:
                history["startDate"] = session["date"]
            return
    raise AssertionError("fixture has no non-execution Friday session")


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


def _remove_factor_diagnostic_row(payload: Payload) -> None:
    payload["factorDiagnostics"]["rankIc"]["rows"].pop()


def _replace_factor_diagnostic_with_alias(payload: Payload) -> None:
    alias = payload["factorDiagnostics"]["scope"]["aliases"][0]["factor"]
    payload["factorDiagnostics"]["rankIc"]["rows"][0]["factor"] = alias


def _alter_factor_diagnostic_mean(payload: Payload) -> None:
    payload["factorDiagnostics"]["rankIc"]["rows"][0]["mean"] = 2.0


def _alter_factor_diagnostic_security_count(payload: Payload) -> None:
    row = payload["factorDiagnostics"]["rankIc"]["rows"][0]
    row["averageSecurityCount"] = row["maximumSecurityCount"] + 1.0


def _alter_factor_diagnostic_peer_count(payload: Payload) -> None:
    payload["factorDiagnostics"]["redundancy"]["rows"][0]["validPeerCount"] -= 1


def _alter_factor_diagnostic_pair_corr(payload: Payload) -> None:
    payload["factorDiagnostics"]["redundancy"]["topPairs"][0]["absCorr"] -= 0.1


def _reverse_factor_diagnostic_pair(payload: Payload) -> None:
    pair = payload["factorDiagnostics"]["redundancy"]["topPairs"][0]
    pair["leftFactor"], pair["rightFactor"] = pair["rightFactor"], pair["leftFactor"]


def _alter_factor_diagnostic_category_mean(payload: Payload) -> None:
    payload["factorDiagnostics"]["categorySummary"][0]["averageMeanRankIc"] += 0.1


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


def test_dashboard_rejects_tampered_python_period_performance(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    selected = payload["selectedFactor"]
    payload["performance"]["periods"][0]["factors"][selected]["cumulativeReturn"] = "bad"

    with pytest.raises(ValueError, match="cumulative return is invalid"):
        _load_payload(payload)


@pytest.mark.parametrize("symbol", ["SPY", "^IXIC", "QQQ"])
def test_dashboard_rejects_full_benchmark_curve_table_mismatch(
    demo_result: AnalysisResult,
    symbol: str,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    performance = payload["performance"]
    full = next(period for period in performance["periods"] if period["key"] == "FULL")
    source_symbol = next(
        candidate
        for candidate, metrics in full["benchmarks"].items()
        if metrics["available"] is True
    )

    # The demo fixture may not provide every optional comparator. Copy one valid
    # benchmark series and its period metrics so each canonical default symbol
    # exercises the same symbol-keyed validator path before the targeted tamper.
    payload["data"]["comparisonBenchmarkAvailability"][symbol] = True
    performance["benchmarkCurves"][symbol] = deepcopy(performance["benchmarkCurves"][source_symbol])
    for period in performance["periods"]:
        period["benchmarks"][symbol] = deepcopy(period["benchmarks"][source_symbol])
    _load_payload(deepcopy(payload))

    full["benchmarks"][symbol]["cumulativeReturn"] += 0.01

    with pytest.raises(ValueError) as exc_info:
        _load_payload(payload)
    assert f"benchmark {symbol} FULL cumulative return" in str(exc_info.value)


def test_dashboard_rejects_full_factor_curve_table_mismatch(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    selected = payload["selectedFactor"]
    full = next(period for period in payload["performance"]["periods"] if period["key"] == "FULL")
    assert full["factors"][selected]["available"] is True
    full["factors"][selected]["cumulativeReturn"] += 0.01

    with pytest.raises(ValueError, match=rf"factor {selected} FULL cumulative return"):
        _load_payload(payload)


def test_dashboard_requires_explicit_unavailable_comparator_reason(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    unavailable = next(
        symbol
        for symbol, available in payload["data"]["comparisonBenchmarkAvailability"].items()
        if not available
    )
    payload["performance"]["periods"][0]["benchmarks"][unavailable]["unavailableReason"] = None

    with pytest.raises(ValueError, match="unavailable period metric"):
        _load_payload(payload)


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
                "comparisonPrices": "e" * 64,
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


def test_dashboard_validates_all_canonical_factor_portfolios_and_selected_parity(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    portfolios = payload["factorPortfolios"]
    canonical_factors = {row["factor"] for row in payload["factorDefinitions"]}

    assert len(portfolios) == payload["meta"]["portfolioCount"] == 64
    assert set(portfolios) == canonical_factors
    assert payload["currentResearchTarget"] == portfolios[payload["selectedFactor"]]
    assert all(
        portfolio["factor"] == factor
        and portfolio["weightingPolicyId"] == payload["selectedWeightingPolicy"]
        and portfolio["weightingPolicyVersion"]
        == POLICY_REGISTRY[payload["selectedWeightingPolicy"]]["version"]
        and portfolio["asOf"] == portfolio["signalDate"] == payload["data"]["asOf"]
        for factor, portfolio in portfolios.items()
    )


@pytest.mark.parametrize(
    "field",
    [
        "investedWeight",
        "cashWeight",
        "riskySleeveHhi",
        "effectiveNames",
        "top1Weight",
        "top5Weight",
        "maxWeight",
    ],
)
def test_dashboard_rejects_each_tampered_factor_portfolio_concentration_field(
    demo_result: AnalysisResult,
    field: str,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    _nonselected_factor_portfolio(payload)["concentration"][field] += 0.01

    with pytest.raises(ValueError, match="factorPortfolios"):
        _load_payload(payload)


def test_dashboard_requires_the_exact_canonical_factor_registry(
    demo_result: AnalysisResult,
) -> None:
    payload = result_payload(demo_result)
    payload["factorDefinitions"] = payload["factorDefinitions"][:-1]

    with pytest.raises(ValueError, match="canonical 64/61/3 registry"):
        _factor_sets(payload)


def test_dashboard_validates_complete_factor_diagnostics_contract(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    diagnostics = payload["factorDiagnostics"]
    rank_ic = diagnostics["rankIc"]
    redundancy = diagnostics["redundancy"]
    alias_factors = {row["factor"] for row in diagnostics["scope"]["aliases"]}

    assert diagnostics["scope"]["independentFactorCount"] == 61
    assert len(rank_ic["rows"]) == len(redundancy["rows"]) == 61
    assert not alias_factors & {row["factor"] for row in rank_ic["rows"]}
    assert rank_ic["horizonSessions"] == 21
    assert rank_ic["overlapping"] is True
    assert redundancy["thresholdAbs"] == pytest.approx(0.95)
    assert redundancy["eligiblePairCount"] <= 61 * 60 // 2
    assert len(redundancy["topPairs"]) == min(10, redundancy["eligiblePairCount"])
    assert any(row["factor"] == payload["selectedFactor"] for row in rank_ic["rows"])


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


def test_dashboard_validates_selected_backtest_holding_history_contract(
    demo_result: AnalysisResult,
) -> None:
    payload = _load_payload(result_payload(demo_result))
    history = payload["selectedBacktestHoldingHistory"]
    held = payload["backtestHeldPortfolio"]

    assert history["contractVersion"] == 1
    assert history["sessionCount"] == len(history["sessions"]) == 21
    assert history["startDate"] == history["sessions"][0]["date"]
    assert history["endDate"] == history["sessions"][-1]["date"] == payload["data"]["asOf"]
    assert history["factor"] == payload["selectedFactor"]
    assert history["weightingPolicyId"] == payload["selectedWeightingPolicy"]
    assert history["sessions"][-1]["cashWeight"] == held["cashWeight"]
    assert history["sessions"][-1]["lastSignalDate"] == held["lastSignalDate"]
    assert history["sessions"][-1]["lastExecutionDate"] == held["lastExecutionDate"]


def test_dashboard_rejects_weekend_substitution_in_selected_holding_history(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    _replace_holding_history_session_with_weekend(payload)

    with pytest.raises(ValueError, match="canonical performance dates"):
        _load_payload(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        _alter_sidecar_factor_policy,
        _alter_sidecar_factor_result_key,
        _alter_sidecar_common_dates,
    ],
)
def test_dashboard_rejects_factor_holding_history_sidecar_provenance_mutations(
    demo_result: AnalysisResult,
    mutate: PayloadMutation,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    mutate(payload)

    with pytest.raises(ValueError, match="factor holding history"):
        _load_payload(payload)


def test_dashboard_rejects_embedded_sidecar_manifest_above_public_limit(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    payload["factorHoldingHistorySidecar"]["bytes"] = MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES + 1

    with pytest.raises(ValueError, match="sidecar manifest is inconsistent"):
        _load_payload(payload)


def test_external_sidecar_validator_fails_closed_above_public_limit(
    demo_result: AnalysisResult,
) -> None:
    payload, sidecar_bytes = externalize_factor_holding_history_sidecar(result_payload(demo_result))
    assert sidecar_bytes is not None
    oversized = b"x" * (MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES + 1)
    manifest = payload["factorHoldingHistorySidecar"]
    manifest["bytes"] = len(oversized)
    manifest["sha256"] = hashlib.sha256(oversized).hexdigest()

    with pytest.raises(ValueError, match="external bytes exceed"):
        validate_factor_holding_history_sidecar_bytes(payload, oversized)


def test_dashboard_writer_fails_closed_before_writing_oversized_sidecar(
    demo_result: AnalysisResult,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = result_payload(demo_result)
    public_payload, sidecar_bytes = externalize_factor_holding_history_sidecar(source)
    assert sidecar_bytes is not None
    oversized = b"x" * (MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES + 1)
    manifest = public_payload["factorHoldingHistorySidecar"]
    manifest["bytes"] = len(oversized)
    manifest["sha256"] = hashlib.sha256(oversized).hexdigest()
    monkeypatch.setattr(
        "momentum_factor_lab.dashboard.externalize_factor_holding_history_sidecar",
        lambda _payload: (public_payload, oversized),
    )
    site_dir = tmp_path / "site"

    with pytest.raises(
        ValueError,
        match=rf"limit is {MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES:,}",
    ):
        write_dashboard_site(source, site_dir)
    assert not site_dir.exists()


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
        _remove_factor_portfolio,
        _alter_factor_portfolio_identity,
        _alter_factor_portfolio_policy_version,
        _alter_factor_portfolio_date,
        _alter_factor_portfolio_status,
        _alter_factor_portfolio_count,
        _alter_factor_portfolio_selection_fraction,
        _alter_factor_portfolio_weight,
        _alter_factor_portfolio_max_weight,
        _alter_factor_portfolio_cash,
        _forge_unavailable_factor_portfolio_without_reason,
        _alter_nonselected_static_grid_portfolio_count,
        _alter_selected_portfolio_deep_parity,
        _alter_current_raw_score,
        _alter_current_weight,
        _alter_current_concentration,
        _alter_selected_current_guardrail_input,
        _alter_held_weight,
        _alter_holding_history_weight_timing,
        _remove_holding_history_session,
        _alter_holding_history_final_weight,
        _alter_holding_history_execution_metadata,
        _replace_holding_history_session_with_weekend,
        _alter_transition_cost,
        _alter_contribution_event,
        _alter_contribution_cross_field,
        _add_legacy_alias,
        _alter_funnel,
        _remove_factor_diagnostic_row,
        _replace_factor_diagnostic_with_alias,
        _alter_factor_diagnostic_mean,
        _alter_factor_diagnostic_security_count,
        _alter_factor_diagnostic_peer_count,
        _alter_factor_diagnostic_pair_corr,
        _reverse_factor_diagnostic_pair,
        _alter_factor_diagnostic_category_mean,
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

    manifest = payload["factorHoldingHistorySidecar"]
    sidecar_path = Path(paths["factorHoldingHistory"])
    sidecar_bytes = sidecar_path.read_bytes()
    assert manifest["storage"] == "external"
    assert "data" not in manifest
    assert manifest["bytes"] == len(sidecar_bytes)
    assert manifest["sha256"] == hashlib.sha256(sidecar_bytes).hexdigest()
    sidecar = validate_factor_holding_history_sidecar_bytes(payload, sidecar_bytes)
    assert set(sidecar["factors"]) == set(payload["factorPortfolios"])
    assert sidecar["dates"] == payload["performance"]["dates"][-21:]


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

    expected = deepcopy(payload)
    expected["factorHoldingHistorySidecar"].pop("data")
    expected["factorHoldingHistorySidecar"]["storage"] = "external"
    assert written == expected
    assert Path(paths["factorHoldingHistory"]).is_file()
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

    assert MAX_DASHBOARD_BYTES == 5_500_000
    assert MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES == 5_000_000
    assert Path(paths["data"]).stat().st_size < MAX_DASHBOARD_BYTES
    assert Path(paths["factorHoldingHistory"]).stat().st_size < (
        MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES
    )


def test_dashboard_rejects_schema_v3_and_compatibility_only_input(
    demo_result: AnalysisResult,
) -> None:
    payload = deepcopy(result_payload(demo_result))
    payload["schemaVersion"] = 3
    payload["factorRanking"] = payload.pop("factorPolicyRanking")

    with pytest.raises(ValueError, match="schemaVersion 4"):
        _load_payload(payload)
