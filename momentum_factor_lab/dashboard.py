from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import fields
from pathlib import Path
from statistics import median
from typing import Any

from .advanced_factors import advanced_factor_definitions_frame
from .config import (
    ABSOLUTE_GUARDRAIL_VERSION,
    JOINT_SELECTION_VERSION,
    POLICY_REGISTRY,
    POLICY_REGISTRY_VERSION,
    RunConfig,
    WEIGHTING_POLICIES,
)
from .data import LIVE_SNAPSHOT_HASH_FIELDS, canonical_records_sha256
from .identity import (
    CANONICAL_JSON_VERSION,
    RESULT_IDENTITY_VERSION,
    canonical_json_bytes,
    canonical_sha256,
)
from .factors import factor_definitions_frame
from .portfolio import capped_weight_values
from .research_inputs import ResearchInputError, ResearchInputs
from .workflow import AnalysisResult, JOINT_TIE_BREAK_POLICY, result_payload


DEFAULT_SITE_TITLE = "Momentum Factor Lab"
WEB_ROOT = Path(__file__).with_name("web")
MAX_DASHBOARD_BYTES = 5_000_000

_LEGACY_SCHEMA_KEYS = {
    "factorRanking",
    "modelPortfolio",
    "policyFactorMetrics",
    "tieBreakPolicy",
    "weightingPolicyComparison",
    "weightingPolicyDefinitions",
    "weightingPolicyReason",
}
_STANDARD_GUARDRAILS = (
    "guardrail_sharpe",
    "guardrail_drawdown",
    "guardrail_cost",
    "guardrail_historical_effective_names",
    "guardrail_current_effective_names",
    "guardrail_historical_target_hhi",
    "guardrail_current_target_hhi",
    "guardrail_historical_target_weight",
    "guardrail_current_target_weight",
    "guardrail_policy_input",
    "guardrail_execution",
    "guardrail_current_target",
    "guardrail_contribution_complete",
)
_CONTRIBUTION_GUARDRAILS = (
    "guardrail_security_day_contribution",
    "guardrail_security_absolute_contribution_share",
    "guardrail_leave_one_security",
)
_POLICY_DIAGNOSTIC_METRICS = (
    "cagr",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "annualized_turnover",
    "annualized_cost_drag",
    "median_target_effective_names",
    "min_target_effective_names",
    "median_target_hhi",
    "max_target_hhi",
    "median_target_cash_weight",
    "median_target_top1_weight",
    "median_target_top5_weight",
    "max_target_weight",
    "max_abs_security_observation_contribution",
    "max_security_absolute_contribution_share",
    "max_abs_leave_one_security_cagr_delta",
)


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _nonnegative_integer(value: object) -> bool:
    return _finite_number(value) and float(value).is_integer() and float(value) >= 0.0


def _required_text(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


def _require_close(observed: object, expected: float, label: str) -> None:
    if not _finite_number(observed) or not _close(float(observed), expected):
        raise ValueError(f"{label} is inconsistent")


def _require_optional_close(observed: object, expected: object, label: str) -> None:
    if _finite_number(expected):
        _require_close(observed, float(expected), label)
    elif observed is not None:
        raise ValueError(f"{label} must be null")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _ratio_severity(observed: float, threshold: float) -> float:
    if observed <= threshold:
        return 0.0
    if threshold <= 0.0:
        return 1.0
    return min(1.0, max(0.0, observed / threshold - 1.0))


def _percentile_rank(values: list[float], position: int) -> float:
    value = values[position]
    lower = sum(candidate < value for candidate in values)
    tied = sum(candidate == value for candidate in values)
    return (lower + (tied + 1.0) / 2.0) / len(values)


def _ascending_average_rank(values: list[float], position: int) -> float:
    value = values[position]
    lower = sum(candidate < value for candidate in values)
    tied = sum(candidate == value for candidate in values)
    return lower + (tied + 1.0) / 2.0


def _validate_identity(payload: dict[str, Any]) -> None:
    identity = payload.get("resultIdentity")
    core_identity_fields = {"identityVersion", "resultKey", "keyParts"}
    transport_identity_fields = {*core_identity_fields, "canonicalKeyPartsJson"}
    if not isinstance(identity, dict):
        raise ValueError("dashboard resultIdentity shape is invalid")
    identity_fields = frozenset(identity)
    if identity_fields not in {
        frozenset(core_identity_fields),
        frozenset(transport_identity_fields),
    }:
        raise ValueError("dashboard resultIdentity shape is invalid")
    key_parts = identity.get("keyParts")
    expected_key_part_fields = {
        "identityVersion",
        "canonicalJsonVersion",
        "analysisCacheVersion",
        "normalizedInputs",
        "marketSnapshot",
        "factorDefinitionSha256",
        "policyDefinitionSha256",
        "selectionSpecSha256",
        "engineSha256",
    }
    if not isinstance(key_parts, dict) or set(key_parts) != expected_key_part_fields:
        raise ValueError("dashboard resultIdentity.keyParts shape is invalid")
    result_key = identity.get("resultKey")
    if (
        identity.get("identityVersion") != RESULT_IDENTITY_VERSION
        or key_parts.get("identityVersion") != RESULT_IDENTITY_VERSION
        or key_parts.get("canonicalJsonVersion") != CANONICAL_JSON_VERSION
        or not _is_sha256(result_key)
        or payload.get("resultKey") != result_key
        or canonical_sha256(key_parts) != result_key
    ):
        raise ValueError("dashboard result identity digest is inconsistent")
    canonical_key_parts_json = identity.get("canonicalKeyPartsJson")
    if canonical_key_parts_json is not None and (
        not isinstance(canonical_key_parts_json, str)
        or canonical_key_parts_json != canonical_json_bytes(key_parts).decode("utf-8")
    ):
        raise ValueError("dashboard result identity canonical transport is inconsistent")
    for field in (
        "factorDefinitionSha256",
        "policyDefinitionSha256",
        "selectionSpecSha256",
        "engineSha256",
    ):
        if not _is_sha256(key_parts.get(field)):
            raise ValueError(f"dashboard resultIdentity.keyParts.{field} is invalid")

    normalized = key_parts.get("normalizedInputs")
    market_snapshot = key_parts.get("marketSnapshot")
    data = payload.get("data")
    config = payload.get("config")
    meta = payload.get("meta")
    if not all(
        isinstance(value, dict) for value in (normalized, market_snapshot, data, config, meta)
    ):
        raise ValueError("dashboard result identity source objects are invalid")
    assert isinstance(normalized, dict)
    assert isinstance(market_snapshot, dict)
    assert isinstance(data, dict)
    assert isinstance(config, dict)
    assert isinstance(meta, dict)
    for field, value in config.items():
        if field in normalized and normalized[field] != value:
            raise ValueError(f"dashboard normalized input {field} differs from config")
    market_fields = {
        "sourceMode": data.get("mode"),
        "sourceLabel": data.get("sourceLabel"),
        "provider": data.get("provider"),
        "priceBasis": data.get("priceBasis"),
        "volumeBasis": data.get("volumeBasis"),
        "rawCloseProxySymbolCount": data.get("rawCloseProxySymbolCount"),
        "requestedThrough": data.get("requestedThrough"),
        "dataAsOf": data.get("asOf"),
        "inputSha256": data.get("inputSha256"),
        "requestedCandidateCount": data.get("requestedCandidateCount"),
        "providerReturnedCandidateCount": data.get("providerReturnedCandidateCount"),
        "analyzedSecurityCount": data.get("analyzedSecurityCount"),
        "candidateSymbolsSha256": canonical_sha256(data.get("analyzedSymbols")),
    }
    if any(market_snapshot.get(field) != value for field, value in market_fields.items()):
        raise ValueError("dashboard result identity market snapshot differs from data")
    meta_digest_fields = {
        "factorDefinitionSha256": "factorDefinitionSha256",
        "policyDefinitionSha256": "policyDefinitionSha256",
        "selectionSpecSha256": "selectionSpecSha256",
    }
    if any(
        key_parts.get(key_field) != meta.get(meta_field)
        for key_field, meta_field in meta_digest_fields.items()
    ):
        raise ValueError("dashboard result identity definition digests differ from meta")


def _validate_data(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    config = payload.get("config")
    if not isinstance(data, dict) or not isinstance(config, dict):
        raise ValueError("dashboard data and config must be objects")
    mode = data.get("mode")
    if mode not in {"live_market", "local_file", "demo"}:
        raise ValueError("dashboard data.mode is unsupported")
    expected_synthetic = mode == "demo"
    if data.get("synthetic") is not expected_synthetic:
        raise ValueError("dashboard data synthetic flag differs from data.mode")
    if config.get("data_mode") != mode:
        raise ValueError("dashboard config.data_mode differs from data.mode")
    as_of = _required_text(data.get("asOf"))
    if not as_of or not _required_text(data.get("startDate")):
        raise ValueError("dashboard data date contract is incomplete")
    if str(data["startDate"]) > as_of:
        raise ValueError("dashboard data date range is inconsistent")
    if not _nonnegative_integer(data.get("observations")) or int(data["observations"]) <= 0:
        raise ValueError("dashboard data observations are invalid")
    count_fields = (
        "requestedCandidateCount",
        "providerReturnedCandidateCount",
        "inputSecurityCount",
        "analyzedSecurityCount",
        "latestEligibleSecurityCount",
    )
    if any(not _nonnegative_integer(data.get(field)) for field in count_fields):
        raise ValueError("dashboard universe-count metadata is invalid")
    if not (
        int(data["latestEligibleSecurityCount"])
        <= int(data["analyzedSecurityCount"])
        <= int(data["inputSecurityCount"])
        <= int(data["providerReturnedCandidateCount"])
        <= int(data["requestedCandidateCount"])
    ):
        raise ValueError("dashboard universe-count funnel is inconsistent")
    funnel = data.get("funnel")
    expected_funnel = {
        "requestedCandidateCount": int(data["requestedCandidateCount"]),
        "providerUsableCandidateCount": int(data["providerReturnedCandidateCount"]),
        "analyzedSecurityCount": int(data["analyzedSecurityCount"]),
        "latestEligibleSecurityCount": int(data["latestEligibleSecurityCount"]),
    }
    if (
        not isinstance(funnel, dict)
        or funnel.get("label") != "canonical_analysis_funnel"
        or funnel.get("authoritative") is not True
        or any(funnel.get(field) != value for field, value in expected_funnel.items())
    ):
        raise ValueError("dashboard canonical data funnel is missing or inconsistent")
    if mode == "live_market":
        input_hashes = data.get("inputSha256")
        read_contract = data.get("snapshotReadContract")
        if (
            data.get("rawCloseAvailable") is not True
            or not isinstance(input_hashes, dict)
            or set(input_hashes) != set(LIVE_SNAPSHOT_HASH_FIELDS)
            or any(not _is_sha256(input_hashes.get(field)) for field in LIVE_SNAPSHOT_HASH_FIELDS)
            or not isinstance(read_contract, dict)
            or read_contract.get("pandasFloatPrecision") != "round_trip"
        ):
            raise ValueError("live_market input snapshot hash contract is incomplete")
        price_sources = payload.get("priceSources")
        source_health = payload.get("sourceHealth")
        if (
            not isinstance(price_sources, list)
            or not price_sources
            or not isinstance(source_health, list)
            or not source_health
            or not _is_sha256(input_hashes.get("priceSources"))
            or not _is_sha256(input_hashes.get("dataSources"))
        ):
            raise ValueError("live_market provider provenance contract is incomplete")
        price_source_symbols: set[str] = set()
        for row in price_sources:
            if not isinstance(row, dict):
                raise ValueError("live_market priceSources contains a non-object row")
            symbol = _required_text(row.get("symbol")).upper()
            source = _required_text(row.get("price_source"))
            if not symbol or not source or symbol in price_source_symbols:
                raise ValueError("live_market priceSources rows are invalid or duplicated")
            price_source_symbols.add(symbol)
        analyzed_symbols = data.get("analyzedSymbols")
        if (
            not isinstance(analyzed_symbols, list)
            or len(analyzed_symbols) != int(data["analyzedSecurityCount"])
            or any(not _required_text(symbol) for symbol in analyzed_symbols)
        ):
            raise ValueError("live_market analyzedSymbols contract is incomplete")
        normalized_analyzed_symbols = [str(symbol).strip().upper() for symbol in analyzed_symbols]
        if len(set(normalized_analyzed_symbols)) != len(normalized_analyzed_symbols) or not set(
            normalized_analyzed_symbols
        ).issubset(price_source_symbols):
            raise ValueError("live_market priceSources do not cover the analyzed universe")
        if any(
            not isinstance(row, dict)
            or not _required_text(row.get("source"))
            or not _required_text(row.get("status"))
            for row in source_health
        ):
            raise ValueError("live_market sourceHealth source/status rows are invalid")
        if (
            canonical_records_sha256(price_sources) != input_hashes["priceSources"]
            or canonical_records_sha256(source_health) != input_hashes["dataSources"]
        ):
            raise ValueError("live_market provider provenance hashes are inconsistent")
    return as_of


def _validate_registry(payload: dict[str, Any]) -> None:
    registry = payload.get("weightingPolicyRegistry")
    if registry != {
        "registryVersion": POLICY_REGISTRY_VERSION,
        "policies": POLICY_REGISTRY,
    }:
        raise ValueError("dashboard weightingPolicyRegistry is not canonical")
    config = payload["config"]
    if config.get("policy_registry_version") != POLICY_REGISTRY_VERSION or config.get(
        "weighting_policies"
    ) != list(WEIGHTING_POLICIES):
        raise ValueError("dashboard configured weighting-policy registry is inconsistent")


def _validate_research_inputs(payload: dict[str, Any]) -> None:
    config = payload["config"]
    run_fields = {field.name for field in fields(RunConfig)}
    try:
        reconstructed = RunConfig(
            **{key: value for key, value in config.items() if key in run_fields}
        )
        expected = ResearchInputs.from_config(reconstructed).to_dict()
    except (TypeError, ResearchInputError) as error:
        raise ValueError("dashboard config cannot reconstruct canonical researchInputs") from error
    if payload.get("researchInputs") != expected:
        raise ValueError("dashboard researchInputs differ from the result-affecting config")


def _factor_sets(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    definitions = payload.get("factorDefinitions")
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("dashboard factorDefinitions must be populated")
    factors: set[str] = set()
    independent: set[str] = set()
    aliases: set[str] = set()
    for definition in definitions:
        if not isinstance(definition, dict) or not _required_text(definition.get("factor")):
            raise ValueError("dashboard factorDefinitions contains an invalid row")
        factor = str(definition["factor"])
        if factor in factors:
            raise ValueError("dashboard factorDefinitions contains duplicate factors")
        factors.add(factor)
        alias_of = definition.get("compatibility_alias_of")
        if alias_of is not None:
            if not _required_text(alias_of) or definition.get("selection_eligible") is not False:
                raise ValueError("dashboard diagnostic alias definition is inconsistent")
            aliases.add(factor)
        elif definition.get("selection_eligible", True) is True:
            independent.add(factor)
    if not independent:
        raise ValueError("dashboard has no independent factor definitions")
    if factors != independent.union(aliases):
        raise ValueError("dashboard contains a non-selectable non-alias factor definition")
    canonical = [
        *factor_definitions_frame().to_dict(orient="records"),
        *advanced_factor_definitions_frame().to_dict(orient="records"),
    ]
    canonical_factors = {str(definition["factor"]) for definition in canonical}
    canonical_aliases = {
        str(definition["factor"])
        for definition in canonical
        if _required_text(definition.get("compatibility_alias_of"))
    }
    canonical_independent = canonical_factors.difference(canonical_aliases)
    if (
        factors != canonical_factors
        or independent != canonical_independent
        or aliases != canonical_aliases
        or len(factors) != 64
        or len(independent) != 61
        or len(aliases) != 3
    ):
        raise ValueError(
            "dashboard factorDefinitions do not satisfy the canonical 64/61/3 registry"
        )
    return independent, aliases


def _guardrail_expectations(row: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    def at_least(field: str, threshold: float) -> bool:
        value = row.get(field)
        return _finite_number(value) and float(value) >= threshold

    def at_most(field: str, threshold: float) -> bool:
        value = row.get(field)
        return _finite_number(value) and float(value) <= threshold

    return {
        "guardrail_sharpe": at_least("sharpe", float(config["selection_min_sharpe"])),
        "guardrail_drawdown": at_least("max_drawdown", -float(config["selection_max_drawdown"])),
        "guardrail_cost": at_most(
            "annualized_cost_drag",
            float(config["selection_max_annualized_cost_drag"]),
        ),
        "guardrail_historical_effective_names": at_least(
            "min_target_effective_names",
            float(config["selection_min_effective_names"]),
        ),
        "guardrail_current_effective_names": at_least(
            "current_target_effective_names",
            float(config["selection_min_effective_names"]),
        ),
        "guardrail_historical_target_hhi": at_most(
            "max_target_hhi", float(config["selection_max_target_hhi"])
        ),
        "guardrail_current_target_hhi": at_most(
            "current_target_hhi", float(config["selection_max_target_hhi"])
        ),
        "guardrail_historical_target_weight": at_most(
            "max_target_weight", float(config["selection_max_target_weight"])
        ),
        "guardrail_current_target_weight": at_most(
            "current_target_max_weight", float(config["selection_max_target_weight"])
        ),
        "guardrail_policy_input": at_least("policy_input_coverage_ratio", 1.0 - 1e-12),
        "guardrail_execution": (
            at_least("execution_coverage_ratio", 1.0 - 1e-12)
            and at_most("blocked_execution_count", 0.0)
            and at_most("total_unpriceable_target_count", 0.0)
        ),
        "guardrail_current_target": row.get("current_portfolio_available") is True,
        "guardrail_contribution_complete": (row.get("contribution_diagnostics_complete") is True),
        "guardrail_security_day_contribution": at_most(
            "max_abs_security_day_contribution",
            float(config["selection_max_abs_security_day_contribution"]),
        ),
        "guardrail_security_absolute_contribution_share": at_most(
            "max_security_absolute_contribution_share",
            float(config["selection_max_security_absolute_contribution_share"]),
        ),
        "guardrail_leave_one_security": at_most(
            "max_abs_leave_one_security_cagr_delta",
            float(config["selection_max_leave_one_security_cagr_delta"]),
        ),
    }


def _selection_sort_key(row: dict[str, Any]) -> tuple[object, ...]:
    descending = (
        "selection_score",
        "base_composite_score",
    )
    later_descending = (
        "sortino",
        "calmar",
        "max_drawdown",
        "cagr",
        "sharpe",
        "stability",
    )
    for field in (
        *descending,
        "max_abs_leave_one_security_cagr_delta",
        "max_abs_security_day_contribution",
        *later_descending,
        "annualized_cost_drag",
        "annualized_turnover",
    ):
        if not _finite_number(row.get(field)):
            raise ValueError(f"eligible factor-policy row has invalid {field}")
    return (
        -float(row["selection_score"]),
        -float(row["base_composite_score"]),
        float(row["max_abs_leave_one_security_cagr_delta"]),
        float(row["max_abs_security_day_contribution"]),
        *(-float(row[field]) for field in later_descending),
        float(row["annualized_cost_drag"]),
        float(row["annualized_turnover"]),
        str(row["factor"]),
        str(row["policy_id"]),
    )


def _validate_grid_and_selection(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    ranking = payload.get("factorPolicyRanking")
    config = payload["config"]
    if (
        not isinstance(ranking, list)
        or not ranking
        or any(not isinstance(row, dict) for row in ranking)
    ):
        raise ValueError("dashboard factorPolicyRanking must be a populated row list")
    rows = [row for row in ranking if isinstance(row, dict)]
    independent, aliases = _factor_sets(payload)
    all_factors = independent.union(aliases)
    pairs: list[tuple[str, str]] = []
    for row in rows:
        factor = _required_text(row.get("factor"))
        policy = _required_text(row.get("policy_id"))
        if factor not in all_factors or policy not in WEIGHTING_POLICIES:
            raise ValueError("dashboard factor-policy grid contains an unexpected pair")
        pairs.append((factor, policy))
    if len(pairs) != len(set(pairs)):
        raise ValueError("dashboard factor-policy grid contains duplicate pairs")
    expected_pairs = {(factor, policy) for factor in all_factors for policy in WEIGHTING_POLICIES}
    if set(pairs) != expected_pairs:
        raise ValueError("dashboard factor-policy grid is incomplete")

    reason_counts: dict[str, int] = {}
    independent_rows = [row for row in rows if str(row["factor"]) in independent]
    for row in independent_rows:
        status = row.get("comparison_status")
        codes = row.get("exclusion_reason_codes")
        if status == "available":
            if codes != []:
                raise ValueError("available independent pair has exclusion reason codes")
        else:
            if (
                not isinstance(codes, list)
                or not codes
                or not all(_required_text(code) for code in codes)
            ):
                raise ValueError("excluded independent pair has no exact reason code")
            for code in codes:
                reason_counts[str(code)] = reason_counts.get(str(code), 0) + 1
    for row in rows:
        if str(row["factor"]) in aliases and row.get("comparison_status") != "duplicate_alias":
            raise ValueError("diagnostic alias pair is not marked duplicate_alias")

    available_count = sum(row.get("comparison_status") == "available" for row in independent_rows)
    common_count = sum(
        all(
            next(
                row
                for row in independent_rows
                if row["factor"] == factor and row["policy_id"] == policy
            ).get("comparison_status")
            == "available"
            for policy in WEIGHTING_POLICIES
        )
        for factor in independent
    )
    expected_grid = {
        "version": 1,
        "independentFactorCount": len(independent),
        "policyCount": len(WEIGHTING_POLICIES),
        "expectedIndependentPairCount": len(independent) * len(WEIGHTING_POLICIES),
        "evaluatedIndependentPairCount": len(independent_rows),
        "availableIndependentPairCount": available_count,
        "excludedIndependentPairCount": len(independent_rows) - available_count,
        "missingIndependentPairCount": 0,
        "diagnosticAliasFactorCount": len(aliases),
        "diagnosticAliasPairCount": len(aliases) * len(WEIGHTING_POLICIES),
        "commonComparableFactorCount": common_count,
        "exclusionReasonCounts": dict(sorted(reason_counts.items())),
        "invariant": (
            "availableIndependentPairCount + excludedIndependentPairCount = "
            "expectedIndependentPairCount"
        ),
    }
    if payload.get("gridAccounting") != expected_grid:
        raise ValueError("dashboard gridAccounting is inconsistent with the unique grid")

    action = config.get("selection_extreme_event_action")
    if action not in {"warn", "penalize", "exclude"}:
        raise ValueError("dashboard extreme-event action is invalid")
    for row in rows:
        expected_guards = _guardrail_expectations(row, config)
        for field, expected in expected_guards.items():
            if row.get(field) is not expected:
                raise ValueError(f"factor-policy {field} is inconsistent")
        standard_pass = all(expected_guards[field] for field in _STANDARD_GUARDRAILS)
        contribution_pass = all(expected_guards[field] for field in _CONTRIBUTION_GUARDRAILS)
        absolute_pass = standard_pass and contribution_pass
        if (
            row.get("standard_guardrail_pass") is not standard_pass
            or row.get("contribution_guardrail_pass") is not contribution_pass
            or row.get("absolute_guardrail_pass") is not absolute_pass
        ):
            raise ValueError("factor-policy aggregate guardrail flags are inconsistent")
        standard_breaches = [
            field.removeprefix("guardrail_")
            for field in _STANDARD_GUARDRAILS
            if not expected_guards[field]
        ]
        contribution_breaches = [
            field.removeprefix("guardrail_")
            for field in _CONTRIBUTION_GUARDRAILS
            if not expected_guards[field]
        ]
        if row.get("guardrail_breaches") != [*standard_breaches, *contribution_breaches]:
            raise ValueError("factor-policy guardrail breach list is inconsistent")
        if row.get("contribution_guardrail_breaches") != contribution_breaches:
            raise ValueError("factor-policy contribution breach list is inconsistent")

        contribution_values = (
            ("max_abs_security_day_contribution", "selection_max_abs_security_day_contribution"),
            (
                "max_security_absolute_contribution_share",
                "selection_max_security_absolute_contribution_share",
            ),
            (
                "max_abs_leave_one_security_cagr_delta",
                "selection_max_leave_one_security_cagr_delta",
            ),
        )
        if any(not _finite_number(row.get(field)) for field, _ in contribution_values):
            raise ValueError("factor-policy contribution diagnostics are not finite")
        expected_penalty = 0.0
        if action == "penalize" and contribution_breaches:
            severity = max(
                _ratio_severity(float(row[field]), float(config[threshold_field]))
                for field, threshold_field in contribution_values
            )
            expected_penalty = float(config["selection_extreme_event_penalty_points"]) * severity
        _require_close(
            row.get("extreme_event_penalty_points"),
            expected_penalty,
            "factor-policy extreme-event penalty",
        )
        _require_optional_close(
            row.get("base_composite_score"),
            row.get("composite_score"),
            "factor-policy base composite score",
        )
        metric_available = row.get("comparison_status") == "available"
        expected_eligible = metric_available and standard_pass
        if action == "exclude":
            expected_eligible = expected_eligible and contribution_pass
        if row.get("selection_eligible") is not expected_eligible:
            raise ValueError("factor-policy selection eligibility is inconsistent")
        if expected_eligible:
            if not _finite_number(row.get("base_composite_score")):
                raise ValueError("eligible factor-policy pair has no base score")
            expected_score = max(0.0, float(row["base_composite_score"]) - expected_penalty)
            _require_close(
                row.get("selection_score"), expected_score, "factor-policy selection score"
            )
        elif row.get("selection_score") is not None:
            raise ValueError("ineligible factor-policy selection score must be null")

        if not metric_available:
            expected_status = "data_excluded"
        elif not standard_pass:
            expected_status = "absolute_guardrail_excluded"
        elif not contribution_pass:
            expected_status = {
                "warn": "extreme_event_warning",
                "penalize": "extreme_event_penalized",
                "exclude": "extreme_event_excluded",
            }[str(action)]
        else:
            expected_status = "eligible"
        if row.get("selection_status") != expected_status:
            raise ValueError("factor-policy selection status is inconsistent")

    ordered = sorted(
        (row for row in rows if row.get("selection_eligible") is True),
        key=_selection_sort_key,
    )
    if not ordered:
        raise ValueError("dashboard has no selection-eligible factor-policy pair")
    for expected_rank, row in enumerate(ordered, start=1):
        if not _finite_number(row.get("rank")) or int(float(row["rank"])) != expected_rank:
            raise ValueError("factor-policy selection rank is inconsistent")
        if row.get("selected") is not (expected_rank == 1):
            raise ValueError("factor-policy selected flag is inconsistent")
    for row in rows:
        if row.get("selection_eligible") is not True and (
            row.get("rank") is not None or row.get("selected") is not False
        ):
            raise ValueError("ineligible factor-policy rank/selected contract is inconsistent")
    selected = ordered[0]
    if rows[0] is not selected:
        raise ValueError("selected factor-policy row must be first in the canonical ranking")
    if (
        payload.get("selectedFactor") != selected.get("factor")
        or payload.get("selectedWeightingPolicy") != selected.get("policy_id")
        or not _required_text(payload.get("selectedReason"))
    ):
        raise ValueError("dashboard selected factor-policy identity is inconsistent")

    meta = payload.get("meta")
    if not isinstance(meta, dict) or any(
        meta.get(field) != expected
        for field, expected in {
            "factorCount": len(all_factors),
            "independentFactorCount": len(independent),
            "availableIndependentPairCount": expected_grid["availableIndependentPairCount"],
            "excludedIndependentPairCount": expected_grid["excludedIndependentPairCount"],
            "aliasFactorCount": len(aliases),
            "policyCount": len(WEIGHTING_POLICIES),
            "policyFactorRunCount": len(rows),
        }.items()
    ):
        raise ValueError("dashboard grid metadata is inconsistent")
    return selected, independent_rows, independent


def _validate_selection_decision(payload: dict[str, Any], selected: dict[str, Any]) -> None:
    config = payload["config"]
    decision = payload.get("selectionDecision")
    performance = payload.get("performance")
    selection_method = payload.get("selectionMethod")
    dates = performance.get("dates") if isinstance(performance, dict) else None
    if not isinstance(decision, dict) or not isinstance(selection_method, dict):
        raise ValueError("dashboard selection decision objects are missing")
    if not isinstance(dates, list) or not dates or not all(_required_text(date) for date in dates):
        raise ValueError("dashboard performance date window is invalid")
    profile = {
        "id": ABSOLUTE_GUARDRAIL_VERSION,
        "version": 1,
        "policyNeutral": True,
        "rules": [
            {
                "id": "minimum_sharpe",
                "metric": "sharpe",
                "operator": ">=",
                "threshold": config["selection_min_sharpe"],
                "unit": "ratio",
            },
            {
                "id": "maximum_drawdown_magnitude",
                "metric": "max_drawdown",
                "operator": ">=",
                "threshold": -float(config["selection_max_drawdown"]),
                "unit": "fraction",
            },
            {
                "id": "maximum_annualized_cost_drag",
                "metric": "annualized_cost_drag",
                "operator": "<=",
                "threshold": config["selection_max_annualized_cost_drag"],
                "unit": "fraction_per_year",
            },
            {
                "id": "minimum_historical_target_effective_names",
                "metric": "min_target_effective_names",
                "operator": ">=",
                "threshold": config["selection_min_effective_names"],
                "unit": "names",
            },
            {
                "id": "minimum_current_target_effective_names",
                "metric": "current_target_effective_names",
                "operator": ">=",
                "threshold": config["selection_min_effective_names"],
                "unit": "names",
            },
            {
                "id": "maximum_historical_target_hhi",
                "metric": "max_target_hhi",
                "operator": "<=",
                "threshold": config["selection_max_target_hhi"],
                "unit": "fraction",
            },
            {
                "id": "maximum_current_target_hhi",
                "metric": "current_target_hhi",
                "operator": "<=",
                "threshold": config["selection_max_target_hhi"],
                "unit": "fraction",
            },
            {
                "id": "maximum_historical_target_weight",
                "metric": "max_target_weight",
                "operator": "<=",
                "threshold": config["selection_max_target_weight"],
                "unit": "fraction",
            },
            {
                "id": "maximum_current_target_weight",
                "metric": "current_target_max_weight",
                "operator": "<=",
                "threshold": config["selection_max_target_weight"],
                "unit": "fraction",
            },
            {
                "id": "maximum_security_day_contribution",
                "metric": "max_abs_security_day_contribution",
                "operator": "<=",
                "threshold": config["selection_max_abs_security_day_contribution"],
                "unit": "portfolio_return_fraction",
            },
            {
                "id": "maximum_security_absolute_contribution_share",
                "metric": "max_security_absolute_contribution_share",
                "operator": "<=",
                "threshold": config["selection_max_security_absolute_contribution_share"],
                "unit": "fraction",
            },
            {
                "id": "maximum_leave_one_security_cagr_delta",
                "metric": "max_abs_leave_one_security_cagr_delta",
                "operator": "<=",
                "threshold": config["selection_max_leave_one_security_cagr_delta"],
                "unit": "cagr_fraction",
            },
        ],
        "requiredContracts": {
            "completePolicyInputs": True,
            "completeExecutionCoverage": True,
            "currentTargetAvailable": True,
            "contributionDiagnosticsComplete": True,
        },
        "extremeEventAction": config["selection_extreme_event_action"],
        "extremeEventPenaltyPoints": config["selection_extreme_event_penalty_points"],
    }
    eligible_count = sum(
        row.get("selection_eligible") is True for row in payload["factorPolicyRanking"]
    )
    exact_fields = {
        "method": "joint_factor_policy",
        "version": JOINT_SELECTION_VERSION,
        "dynamicSelection": True,
        "selectedFactor": selected["factor"],
        "selectedPolicyId": selected["policy_id"],
        "selectedPolicyVersion": POLICY_REGISTRY[str(selected["policy_id"])]["version"],
        "guardrailProfile": profile,
        "tieBreakPolicy": list(JOINT_TIE_BREAK_POLICY),
        "reason": payload["selectedReason"],
        "evaluationStart": dates[0],
        "evaluationEnd": dates[-1],
        "evaluationWindowDays": len(dates),
        "minimumObservations": config["min_evaluation_observations"],
        "minimumValuationCoverage": config["min_valuation_coverage"],
        "minimumDailyRiskObservations": config["min_daily_risk_observations"],
        "selectionEligiblePairCount": eligible_count,
        "gridAccounting": payload["gridAccounting"],
    }
    if any(decision.get(field) != value for field, value in exact_fields.items()):
        raise ValueError("dashboard joint selection decision is inconsistent")
    score_fields = {
        "selectedBaseCompositeScore": "base_composite_score",
        "selectedExtremeEventPenaltyPoints": "extreme_event_penalty_points",
        "selectedSelectionScore": "selection_score",
    }
    for decision_field, row_field in score_fields.items():
        _require_close(
            decision.get(decision_field),
            float(selected[row_field]),
            f"selectionDecision.{decision_field}",
        )
    expected_method = {
        "name": "joint_factor_policy_absolute_guardrails",
        "version": JOINT_SELECTION_VERSION,
        "guardrailVersion": ABSOLUTE_GUARDRAIL_VERSION,
        "evaluationWindowDays": len(dates),
        "minimumObservations": config["min_evaluation_observations"],
        "minimumValuationCoverage": config["min_valuation_coverage"],
        "minimumDailyRiskObservations": config["min_daily_risk_observations"],
        "weights": config["score_weights"],
        "netOfCosts": True,
        "signalTiming": "close_t",
        "executionTiming": "next_session_close",
        "returnExposureStarts": "following_close_to_close_session",
        "tieBreakPolicy": list(JOINT_TIE_BREAK_POLICY),
        "policyAggregatesAreDiagnosticOnly": True,
        "equalWeightIsPeerCandidate": True,
    }
    if selection_method != expected_method:
        raise ValueError("dashboard selectionMethod is inconsistent")
    if (
        not isinstance(performance, dict)
        or performance.get("weightingPolicyId") != selected["policy_id"]
        or not isinstance(performance.get("factorCurves"), dict)
        or selected["factor"] not in performance["factorCurves"]
        or len(performance["factorCurves"][selected["factor"]]) != len(dates)
    ):
        raise ValueError("dashboard selected performance curve is inconsistent")


def _validate_policy_diagnostics(
    payload: dict[str, Any],
    independent_rows: list[dict[str, Any]],
    independent: set[str],
) -> None:
    diagnostics = payload.get("policyDiagnostics")
    selected_factor = str(payload["selectedFactor"])
    selected_policy = str(payload["selectedWeightingPolicy"])
    if not isinstance(diagnostics, list) or len(diagnostics) != len(WEIGHTING_POLICIES):
        raise ValueError("dashboard policyDiagnostics has an invalid policy count")
    available_sets = {
        policy: {
            str(row["factor"])
            for row in independent_rows
            if row["policy_id"] == policy and row.get("comparison_status") == "available"
        }
        for policy in WEIGHTING_POLICIES
    }
    common = set.intersection(*(available_sets[policy] for policy in WEIGHTING_POLICIES))
    expected_diagnostic_fields = {
        "policy_id",
        "policy_version",
        "diagnostic_only",
        "paired_factor_count",
        "available_factor_count",
        "excluded_factor_count",
        "data_status",
        "contains_selected_pair",
        "selected_factor_if_policy",
        "current_available_independent_factor_count",
        "current_median_holding_count",
        "current_median_cash_weight",
        *_POLICY_DIAGNOSTIC_METRICS,
    }
    for position, policy in enumerate(WEIGHTING_POLICIES):
        row = diagnostics[position]
        if not isinstance(row, dict) or row.get("policy_id") != policy:
            raise ValueError("dashboard policyDiagnostics order/identity is inconsistent")
        if set(row) != expected_diagnostic_fields:
            raise ValueError("dashboard policyDiagnostics contains non-canonical fields")
        frame = [item for item in independent_rows if item["policy_id"] == policy]
        paired = [item for item in frame if str(item["factor"]) in common]
        expected = {
            "policy_version": POLICY_REGISTRY[policy]["version"],
            "diagnostic_only": True,
            "paired_factor_count": len(paired),
            "available_factor_count": len(available_sets[policy]),
            "excluded_factor_count": len(independent) - len(available_sets[policy]),
            "data_status": (
                "complete" if len(available_sets[policy]) == len(independent) else "partial"
            ),
            "contains_selected_pair": policy == selected_policy,
            "selected_factor_if_policy": selected_factor if policy == selected_policy else None,
            "current_available_independent_factor_count": sum(
                item.get("current_portfolio_available") is True for item in frame
            ),
        }
        if any(row.get(field) != value for field, value in expected.items()):
            raise ValueError("dashboard policy diagnostic counts/identity are inconsistent")
        if not paired:
            raise ValueError("dashboard policy diagnostics have no common comparable factors")
        for field in (
            "current_holding_count",
            "current_cash_weight",
            *_POLICY_DIAGNOSTIC_METRICS,
        ):
            values = [item.get(field) for item in paired]
            if any(not _finite_number(value) for value in values):
                raise ValueError(f"dashboard common policy metric {field} is not finite")
            output_field = {
                "current_holding_count": "current_median_holding_count",
                "current_cash_weight": "current_median_cash_weight",
            }.get(field, field)
            _require_close(
                row.get(output_field),
                float(median(float(value) for value in values)),
                f"policyDiagnostics[{policy}].{output_field}",
            )
    aggregate = payload.get("portfolioPolicy", {}).get("policyAggregateDiagnostics")
    expected_aggregate = {
        "diagnosticOnly": True,
        "selectedByPolicyAggregate": False,
        "policyCount": len(WEIGHTING_POLICIES),
        "commonComparableFactorCount": len(common),
    }
    if (
        not isinstance(aggregate, dict)
        or set(aggregate) != {*expected_aggregate, "note"}
        or any(aggregate.get(field) != value for field, value in expected_aggregate.items())
        or not _required_text(aggregate.get("note"))
    ):
        raise ValueError("dashboard policy aggregate diagnostics are inconsistent")


def _validate_concentration(portfolio: dict[str, Any], label: str) -> None:
    concentration = portfolio.get("concentration")
    if not isinstance(concentration, dict):
        raise ValueError(f"{label} is missing concentration diagnostics")
    weights = [float(row["weight"]) for row in portfolio["weights"]]
    cash = float(portfolio["cashWeight"])
    invested = sum(weights)
    normalized = [weight / invested for weight in weights] if invested > 0.0 else []
    hhi = sum(weight * weight for weight in normalized)
    ordered = sorted(weights, reverse=True)
    expected = {
        "investedWeight": invested,
        "cashWeight": cash,
        "riskySleeveHhi": hhi,
        "effectiveNames": (1.0 / hhi if hhi > 0.0 else 0.0),
        "top1Weight": sum(ordered[:1]),
        "top5Weight": sum(ordered[:5]),
        "maxWeight": (ordered[0] if ordered else 0.0),
    }
    for field, value in expected.items():
        _require_close(concentration.get(field), value, f"{label} concentration.{field}")


def _validate_policy_weight_construction(
    portfolio: dict[str, Any],
    *,
    policy_id: str,
    config: dict[str, Any],
    label: str,
) -> None:
    weights = portfolio["weights"]
    factor_scores = [float(row["factorScore"]) for row in weights]
    if any(left < right for left, right in zip(factor_scores, factor_scores[1:])):
        raise ValueError(f"{label} factor scores are not ordered descending")
    component_status = portfolio["componentStatus"]
    rank_components: list[float] = []
    for position, row in enumerate(weights):
        expected_rank_component = _ascending_average_rank(factor_scores, position)
        _require_close(
            row.get("rankComponent"),
            expected_rank_component,
            f"{label} rank component",
        )
        rank_components.append(expected_rank_component)

    score_components: list[float] | None = None
    liquidity_components: list[float] | None = None
    if policy_id == "score_liquidity_rank":
        scoring_values = [max(value, 0.0) for value in factor_scores]
        if not any(value > 0.0 for value in scoring_values):
            scoring_values = factor_scores
        liquidity_values = [row.get("trailingDollarVolume") for row in weights]
        if any(not _finite_number(value) or float(value) <= 0.0 for value in liquidity_values):
            raise ValueError(f"{label} trailing liquidity inputs are invalid")
        score_components = [
            _percentile_rank(scoring_values, position) for position in range(len(weights))
        ]
        liquidity_numbers = [float(value) for value in liquidity_values]
        liquidity_components = [
            _percentile_rank(liquidity_numbers, position) for position in range(len(weights))
        ]

    raw_values: list[float] = []
    for position, row in enumerate(weights):
        rank_component = rank_components[position]
        if policy_id == "equal_weight":
            if (
                component_status.get("rank") != "not_used"
                or component_status.get("volatility") != "not_used"
            ):
                raise ValueError(f"{label} equal-weight component status is inconsistent")
            expected_raw = 1.0
        elif policy_id == "capped_linear_rank":
            if (
                component_status.get("rank") != "available"
                or component_status.get("volatility") != "not_used"
            ):
                raise ValueError(f"{label} linear-rank component status is inconsistent")
            expected_raw = rank_component
        elif policy_id == "capped_vol_adjusted_rank":
            volatility = row.get("trailingVolatility")
            if (
                component_status.get("rank") != "available"
                or component_status.get("volatility") != "trailing_signal_date_only"
                or not _finite_number(volatility)
                or not float(config["volatility_floor"])
                <= float(volatility)
                <= float(config["volatility_cap"])
            ):
                raise ValueError(f"{label} volatility-adjusted components are inconsistent")
            expected_raw = rank_component / float(volatility)
        elif policy_id == "score_liquidity_rank":
            if (
                component_status.get("rank") != "available"
                or component_status.get("liquidity") != "trailing_raw_dollar_volume"
                or score_components is None
                or liquidity_components is None
            ):
                raise ValueError(f"{label} score-liquidity component status is inconsistent")
            _require_close(
                row.get("scoreComponent"),
                score_components[position],
                f"{label} score component",
            )
            _require_close(
                row.get("liquidityComponent"),
                liquidity_components[position],
                f"{label} liquidity component",
            )
            expected_raw = (
                float(config["score_liquidity_rank_floor"])
                + float(config["score_liquidity_score_weight"]) * score_components[position]
                + float(config["score_liquidity_liquidity_weight"]) * liquidity_components[position]
            )
        else:  # pragma: no cover - registry validation prevents this branch
            raise ValueError(f"unsupported weighting policy: {policy_id}")
        _require_close(row.get("rawPolicyScore"), expected_raw, f"{label} raw policy score")
        raw_values.append(expected_raw)

    raw_total = sum(raw_values)
    expected_weights = capped_weight_values(raw_values, float(config["max_weight"]))
    for row, raw_value, expected_weight in zip(weights, raw_values, expected_weights, strict=True):
        _require_close(row.get("preCapWeight"), raw_value / raw_total, f"{label} pre-cap weight")
        _require_close(row.get("weight"), expected_weight, f"{label} capped weight")
        _require_close(row.get("maxWeight"), float(config["max_weight"]), f"{label} max weight")
        expected_binding = expected_weight >= float(config["max_weight"]) - 1e-12
        if row.get("capBinding") is not expected_binding:
            raise ValueError(f"{label} cap-binding flag is inconsistent")


def _validate_current_target(
    payload: dict[str, Any], *, as_of: str, selected: dict[str, Any]
) -> dict[str, Any]:
    target = payload.get("currentResearchTarget")
    config = payload["config"]
    factor = str(selected["factor"])
    policy = str(selected["policy_id"])
    label = "currentResearchTarget"
    if (
        not isinstance(target, dict)
        or target.get("factor") != factor
        or target.get("weightingPolicyId") != policy
        or target.get("weightingPolicyVersion") != POLICY_REGISTRY[policy]["version"]
        or target.get("asOf") != as_of
        or target.get("signalDate") != as_of
        or target.get("targetType") != "current_research_target"
        or target.get("executionTiming") != "next_available_session_close_after_signal"
        or target.get("status") != "available"
        or not _required_text(target.get("tieBreakPolicy"))
        or not isinstance(target.get("componentStatus"), dict)
        or target["componentStatus"].get("score") != "available"
        or not isinstance(target.get("reasons"), list)
        or not all(_required_text(reason) for reason in target["reasons"])
    ):
        raise ValueError("dashboard currentResearchTarget identity/status is inconsistent")
    weights = target.get("weights")
    if not isinstance(weights, list) or not weights:
        raise ValueError("dashboard currentResearchTarget has no selected allocation")
    selected_count = target.get("selectedSecurityCount")
    eligible_count = target.get("eligibleSecurityCount")
    if (
        not _nonnegative_integer(selected_count)
        or int(selected_count) != len(weights)
        or not _nonnegative_integer(eligible_count)
        or int(eligible_count) < len(weights)
        or len(weights) > int(config["top_n"])
    ):
        raise ValueError("dashboard currentResearchTarget counts are inconsistent")
    symbols: list[str] = []
    total = 0.0
    for expected_rank, row in enumerate(weights, start=1):
        if (
            not isinstance(row, dict)
            or row.get("rank") != expected_rank
            or not _required_text(row.get("symbol"))
            or not _required_text(row.get("name"))
            or row.get("eligibilityStatus") != "eligible"
            or not _finite_number(row.get("factorScore"))
            or not _finite_number(row.get("latestPrice"))
            or float(row["latestPrice"]) <= 0.0
            or not _finite_number(row.get("weight"))
            or not 0.0 < float(row["weight"]) <= float(config["max_weight"]) + 1e-12
        ):
            raise ValueError("dashboard currentResearchTarget contains an invalid holding")
        symbols.append(str(row["symbol"]))
        total += float(row["weight"])
    if len(symbols) != len(set(symbols)):
        raise ValueError("dashboard currentResearchTarget contains duplicate symbols")
    cash = target.get("cashWeight")
    if (
        not _finite_number(cash)
        or not 0.0 <= float(cash) <= 1.0
        or not _close(total + float(cash), 1.0)
    ):
        raise ValueError("dashboard currentResearchTarget weights plus cash are inconsistent")
    _require_close(
        target.get("selectionFraction"),
        len(weights) / int(eligible_count) if int(eligible_count) else 0.0,
        "currentResearchTarget.selectionFraction",
    )
    _validate_policy_weight_construction(
        target,
        policy_id=policy,
        config=config,
        label=label,
    )
    _validate_concentration(target, label)
    return target


def _validate_backtest_held_portfolio(
    payload: dict[str, Any],
    *,
    as_of: str,
    selected_factor: str,
    selected_policy: str,
) -> dict[str, Any]:
    held = payload.get("backtestHeldPortfolio")
    if (
        not isinstance(held, dict)
        or held.get("factor") != selected_factor
        or held.get("weightingPolicyId") != selected_policy
        or held.get("asOf") != as_of
        or not _required_text(held.get("lastSignalDate"))
        or not _required_text(held.get("lastExecutionDate"))
        or not isinstance(held.get("valuationAvailable"), bool)
        or not isinstance(held.get("weights"), list)
        or not _finite_number(held.get("cashWeight"))
        or not 0.0 <= float(held["cashWeight"]) <= 1.0
    ):
        raise ValueError("dashboard backtestHeldPortfolio contract is inconsistent")
    weights = held["weights"]
    if not (str(held["lastSignalDate"]) <= str(held["lastExecutionDate"]) <= as_of):
        raise ValueError("dashboard backtestHeldPortfolio dates are inconsistent")
    if held["valuationAvailable"] is True and not weights:
        raise ValueError("dashboard valued backtestHeldPortfolio has no holdings")
    symbols: list[str] = []
    total = float(held["cashWeight"])
    for expected_rank, row in enumerate(weights, start=1):
        if (
            not isinstance(row, dict)
            or row.get("rank") != expected_rank
            or not _required_text(row.get("symbol"))
            or not _required_text(row.get("name"))
            or not _finite_number(row.get("weight"))
            or not 0.0 < float(row["weight"]) <= 1.0
            or (row.get("factorScore") is not None and not _finite_number(row.get("factorScore")))
            or (
                held["valuationAvailable"] is True
                and (not _finite_number(row.get("latestPrice")) or float(row["latestPrice"]) <= 0.0)
            )
        ):
            raise ValueError("dashboard backtestHeldPortfolio has an invalid holding")
        symbols.append(str(row["symbol"]))
        total += float(row["weight"])
    if len(symbols) != len(set(symbols)):
        raise ValueError("dashboard backtestHeldPortfolio contains duplicate symbols")
    if not _close(total, 1.0):
        raise ValueError("dashboard backtestHeldPortfolio weights plus cash do not sum to 1")
    return held


def _validate_current_transition(
    payload: dict[str, Any],
    *,
    held: dict[str, Any],
    target: dict[str, Any],
    as_of: str,
) -> None:
    transition = payload.get("currentTransition")
    config = payload["config"]
    valuation_available = held["valuationAvailable"]
    if (
        not isinstance(transition, dict)
        or transition.get("asOf") != as_of
        or transition.get("targetSignalDate") != target.get("signalDate")
        or transition.get("expectedExecutionTiming") != target.get("executionTiming")
        or transition.get("actualNextClosePretradeDriftKnown") is not False
        or transition.get("valuationAvailable") is not valuation_available
        or not _finite_number(transition.get("pretradeCashWeight"))
        or not _close(float(transition["pretradeCashWeight"]), float(held["cashWeight"]))
        or not _finite_number(transition.get("targetCashWeight"))
        or not _close(float(transition["targetCashWeight"]), float(target["cashWeight"]))
        or not _finite_number(transition.get("totalCostBps"))
        or not _close(float(transition["totalCostBps"]), float(config["total_cost_bps"]))
        or transition.get("turnoverFormula")
        != "0.5*(sum_abs_target_minus_pretrade_stock+abs_target_minus_pretrade_cash)"
        or transition.get("costFormula") != "one_way_turnover*total_cost_bps/10000"
    ):
        raise ValueError("dashboard currentTransition contract is inconsistent")
    if valuation_available is not True:
        if (
            transition.get("status") != "unavailable_latest_held_valuation_incomplete"
            or _finite_number(transition.get("oneWayTurnover"))
            or _finite_number(transition.get("modeledCostFraction"))
        ):
            raise ValueError("dashboard unavailable currentTransition is inconsistent")
        return
    held_weights = {str(row["symbol"]): float(row["weight"]) for row in held["weights"]}
    target_weights = {str(row["symbol"]): float(row["weight"]) for row in target["weights"]}
    symbols = set(held_weights).union(target_weights)
    expected_turnover = 0.5 * (
        sum(
            abs(target_weights.get(symbol, 0.0) - held_weights.get(symbol, 0.0))
            for symbol in symbols
        )
        + abs(float(target["cashWeight"]) - float(held["cashWeight"]))
    )
    expected_cost = expected_turnover * float(config["total_cost_bps"]) / 10_000.0
    if transition.get("status") != "indicative_as_of_close":
        raise ValueError("dashboard currentTransition status is inconsistent")
    _require_close(
        transition.get("oneWayTurnover"), expected_turnover, "currentTransition turnover"
    )
    _require_close(
        transition.get("modeledCostFraction"), expected_cost, "currentTransition modeled cost"
    )


def _validate_contribution_event(event: object, label: str, *, exact: bool) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError(f"{label} is missing")
    if (
        not _required_text(event.get("symbol"))
        or not _required_text(event.get("date"))
        or (
            event.get("intervalStart") is not None
            and not _required_text(event.get("intervalStart"))
        )
        or not _nonnegative_integer(event.get("returnIntervalSessions"))
        or int(event["returnIntervalSessions"]) < 1
        or (exact and int(event["returnIntervalSessions"]) != 1)
    ):
        raise ValueError(f"{label} identity/date interval is invalid")
    for field in (
        "contribution",
        "absoluteContribution",
        "startWeight",
        "securityReturn",
        "portfolioReturn",
    ):
        if not _finite_number(event.get(field)):
            raise ValueError(f"{label}.{field} is not finite")
    if (
        float(event["absoluteContribution"]) < 0.0
        or not _close(float(event["absoluteContribution"]), abs(float(event["contribution"])))
        or not 0.0 <= float(event["startWeight"]) <= 1.0
    ):
        raise ValueError(f"{label} contribution arithmetic is inconsistent")
    return event


def _validate_leave_one(row: object, label: str) -> dict[str, Any]:
    if not isinstance(row, dict) or not _required_text(row.get("symbol")):
        raise ValueError(f"{label} identity is invalid")
    if (
        row.get("method") != "frozen_realized_contribution_deletion"
        or row.get("reoptimized") is not False
    ):
        raise ValueError(f"{label} method contract is invalid")
    for field in ("baseCagr", "leaveOneCagr", "cagrDelta", "absoluteCagrDelta"):
        if not _finite_number(row.get(field)):
            raise ValueError(f"{label}.{field} is not finite")
    if not _close(
        float(row["cagrDelta"]), float(row["baseCagr"]) - float(row["leaveOneCagr"])
    ) or not _close(float(row["absoluteCagrDelta"]), abs(float(row["cagrDelta"]))):
        raise ValueError(f"{label} CAGR arithmetic is inconsistent")
    return row


def _validate_contribution_diagnostics(payload: dict[str, Any], selected: dict[str, Any]) -> None:
    diagnostics = payload.get("contributionDiagnostics")
    if not isinstance(diagnostics, dict):
        raise ValueError("dashboard contributionDiagnostics is missing")
    if (
        not _required_text(diagnostics.get("attributionMethod"))
        or not _required_text(diagnostics.get("attributionVersion"))
        or diagnostics.get("complete") is not True
        or diagnostics.get("reason") is not None
        or diagnostics.get("observedReturnsPreserved") is not True
        or diagnostics.get("reoptimized") is not False
        or not _required_text(diagnostics.get("evaluationStart"))
        or not _required_text(diagnostics.get("evaluationEnd"))
        or not _nonnegative_integer(diagnostics.get("activeCalendarObservations"))
        or not _nonnegative_integer(diagnostics.get("observedReturnCount"))
        or int(diagnostics["observedReturnCount"]) > int(diagnostics["activeCalendarObservations"])
    ):
        raise ValueError("dashboard contributionDiagnostics contract is inconsistent")
    exact_event = _validate_contribution_event(
        diagnostics.get("maxExactSingleSessionSecurityContribution"),
        "contributionDiagnostics.maxExactSingleSessionSecurityContribution",
        exact=True,
    )
    observed_event = _validate_contribution_event(
        diagnostics.get("maxObservedIntervalSecurityContribution"),
        "contributionDiagnostics.maxObservedIntervalSecurityContribution",
        exact=False,
    )
    _require_close(
        diagnostics.get("maxAbsSecurityDayContribution"),
        float(exact_event["absoluteContribution"]),
        "contributionDiagnostics.maxAbsSecurityDayContribution",
    )
    largest = diagnostics.get("largestAbsoluteContributionSecurity")
    if not isinstance(largest, dict) or not _required_text(largest.get("symbol")):
        raise ValueError("dashboard largest absolute contribution security is invalid")
    for field in (
        "signedContribution",
        "absoluteContribution",
        "absoluteContributionShare",
    ):
        if not _finite_number(largest.get(field)):
            raise ValueError(f"dashboard largest contribution {field} is not finite")
    for field in (
        "maxSecurityAbsoluteContributionShare",
        "totalAbsoluteSecurityContribution",
        "absoluteContributionHhi",
        "maxLeaveOneSecurityCagrDelta",
        "attributionMaxResidual",
    ):
        if not _finite_number(diagnostics.get(field)) or float(diagnostics[field]) < 0.0:
            raise ValueError(f"dashboard contributionDiagnostics.{field} is invalid")
    if (
        not 0.0 <= float(largest["absoluteContributionShare"]) <= 1.0
        or not 0.0 <= float(diagnostics["maxSecurityAbsoluteContributionShare"]) <= 1.0
        or not 0.0 <= float(diagnostics["absoluteContributionHhi"]) <= 1.0
    ):
        raise ValueError("dashboard contribution share/HHI is outside [0, 1]")
    _require_close(
        diagnostics.get("maxSecurityAbsoluteContributionShare"),
        float(largest["absoluteContributionShare"]),
        "contributionDiagnostics.maxSecurityAbsoluteContributionShare",
    )
    total_absolute = float(diagnostics["totalAbsoluteSecurityContribution"])
    if total_absolute > 0.0:
        _require_close(
            largest.get("absoluteContributionShare"),
            float(largest["absoluteContribution"]) / total_absolute,
            "largestAbsoluteContributionSecurity.absoluteContributionShare",
        )

    max_leave_one = _validate_leave_one(
        diagnostics.get("maxLeaveOneSecurity"),
        "contributionDiagnostics.maxLeaveOneSecurity",
    )
    _require_close(
        diagnostics.get("maxLeaveOneSecurityCagrDelta"),
        float(max_leave_one["absoluteCagrDelta"]),
        "contributionDiagnostics.maxLeaveOneSecurityCagrDelta",
    )
    top = diagnostics.get("topLeaveOneSecurity")
    if not isinstance(top, list) or not top or len(top) > 10:
        raise ValueError("dashboard topLeaveOneSecurity list is invalid")
    validated_top = [
        _validate_leave_one(row, f"contributionDiagnostics.topLeaveOneSecurity[{position}]")
        for position, row in enumerate(top)
    ]
    if validated_top[0] != max_leave_one:
        raise ValueError("dashboard maxLeaveOneSecurity differs from the first top sensitivity")
    expected_order = sorted(
        validated_top,
        key=lambda row: (-float(row["absoluteCagrDelta"]), str(row["symbol"])),
    )
    if validated_top != expected_order:
        raise ValueError("dashboard top leave-one-security sensitivities are not ordered")

    cross_fields = {
        "contribution_diagnostics_complete": diagnostics["complete"],
        "contribution_attribution_method": diagnostics["attributionMethod"],
        "contribution_attribution_version": diagnostics["attributionVersion"],
    }
    if any(selected.get(field) != value for field, value in cross_fields.items()):
        raise ValueError("selected pair contribution diagnostic identity differs from detail")
    scalar_cross_fields = {
        "max_abs_security_day_contribution": diagnostics["maxAbsSecurityDayContribution"],
        "max_abs_security_observation_contribution": observed_event["absoluteContribution"],
        "max_security_absolute_contribution_share": diagnostics[
            "maxSecurityAbsoluteContributionShare"
        ],
        "absolute_contribution_hhi": diagnostics["absoluteContributionHhi"],
        "max_abs_leave_one_security_cagr_delta": diagnostics["maxLeaveOneSecurityCagrDelta"],
        "attribution_max_residual": diagnostics["attributionMaxResidual"],
    }
    for field, value in scalar_cross_fields.items():
        _require_close(selected.get(field), float(value), f"selected pair {field}")
    decision = payload["selectionDecision"]
    if (
        diagnostics["evaluationStart"] != decision["evaluationStart"]
        or diagnostics["evaluationEnd"] != decision["evaluationEnd"]
    ):
        raise ValueError("dashboard contribution diagnostic window differs from selection window")


def _validate_portfolio_policy(payload: dict[str, Any], selected: dict[str, Any]) -> None:
    policy = payload.get("portfolioPolicy")
    config = payload["config"]
    selected_policy = str(selected["policy_id"])
    expected_history = {
        "targetWeightKernel": True,
        "capAndCashContract": True,
        "turnoverFormula": "same_cash_inclusive_half_l1",
        "costFormula": "same_turnover_times_total_cost_rate",
        "historicalRebalanceGridRequired": True,
        "currentTransitionBasis": "latest_observed_close_indicative",
        "actualNextCloseTransitionKnown": False,
    }
    expected_parameters = {
        "topN": config["top_n"],
        "maxWeight": config["max_weight"],
        "rebalanceFrequency": config["rebalance_frequency"],
        "transactionCostBps": config["transaction_cost_bps"],
        "slippageBps": config["slippage_bps"],
        "volatilityLookbackDays": config["volatility_lookback_days"],
        "volatilityFloor": config["volatility_floor"],
        "volatilityCap": config["volatility_cap"],
    }
    if (
        not isinstance(policy, dict)
        or policy.get("selectedPolicyId") != selected_policy
        or policy.get("version") != POLICY_REGISTRY[selected_policy]["version"]
        or policy.get("selectedReason") != payload["selectedReason"]
        or policy.get("historyCurrentParity") != expected_history
        or policy.get("parameters") != expected_parameters
    ):
        raise ValueError("dashboard portfolioPolicy contract is inconsistent")


def _load_payload(source: AnalysisResult | dict[str, Any] | Path) -> dict[str, Any]:
    if isinstance(source, AnalysisResult):
        payload = result_payload(source)
    elif isinstance(source, Path):
        payload = json.loads(source.read_text(encoding="utf-8"))
    else:
        payload = source
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 4:
        raise ValueError("dashboard payload must use schemaVersion 4")
    required = {
        "resultKey",
        "resultIdentity",
        "generatedAtUtc",
        "selectedFactor",
        "selectedWeightingPolicy",
        "selectedReason",
        "selectionDecision",
        "gridAccounting",
        "factorPolicyRanking",
        "policyDiagnostics",
        "weightingPolicyRegistry",
        "contributionDiagnostics",
        "portfolioPolicy",
        "researchScope",
        "researchInputs",
        "config",
        "data",
        "selectionMethod",
        "currentResearchTarget",
        "backtestHeldPortfolio",
        "currentTransition",
        "factorDefinitions",
        "performance",
        "meta",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError("dashboard payload missing fields: " + ", ".join(missing))
    legacy = sorted(_LEGACY_SCHEMA_KEYS.intersection(payload))
    if legacy:
        raise ValueError("dashboard schemaVersion 4 contains legacy aliases: " + ", ".join(legacy))
    if not _required_text(payload.get("generatedAtUtc")):
        raise ValueError("dashboard generatedAtUtc is required")
    _validate_data(payload)
    _validate_identity(payload)
    _validate_registry(payload)
    _validate_research_inputs(payload)
    selected, independent_rows, independent = _validate_grid_and_selection(payload)
    _validate_selection_decision(payload, selected)
    _validate_policy_diagnostics(payload, independent_rows, independent)
    _validate_portfolio_policy(payload, selected)
    as_of = str(payload["data"]["asOf"])
    target = _validate_current_target(payload, as_of=as_of, selected=selected)
    selected_current_fields = {
        "current_holding_count": target["selectedSecurityCount"],
        "current_cash_weight": target["cashWeight"],
        "current_target_effective_names": target["concentration"]["effectiveNames"],
        "current_target_hhi": target["concentration"]["riskySleeveHhi"],
        "current_target_max_weight": target["concentration"]["maxWeight"],
    }
    for field, value in selected_current_fields.items():
        _require_close(selected.get(field), float(value), f"selected pair {field}")
    held = _validate_backtest_held_portfolio(
        payload,
        as_of=as_of,
        selected_factor=str(selected["factor"]),
        selected_policy=str(selected["policy_id"]),
    )
    _validate_current_transition(payload, held=held, target=target, as_of=as_of)
    _validate_contribution_diagnostics(payload, selected)
    return payload


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    selected = next(row for row in payload["factorPolicyRanking"] if row.get("selected") is True)
    target = payload["currentResearchTarget"]
    data = payload["data"]
    scope = payload["researchScope"]
    meta = payload["meta"]
    return {
        "schemaVersion": 4,
        "contract": "quant-research-summary",
        "contractVersion": 3,
        "projectId": "momentum-factor-lab",
        "resultKey": payload["resultKey"],
        "resultIdentity": payload["resultIdentity"],
        "generatedAt": payload["generatedAtUtc"],
        "dataAsOf": data["asOf"],
        "dataMode": data["mode"],
        "sourceLabel": data["sourceLabel"],
        "synthetic": data["synthetic"],
        "requestedCandidateCount": data["requestedCandidateCount"],
        "providerReturnedCandidateCount": data["providerReturnedCandidateCount"],
        "universeSize": data["inputSecurityCount"],
        "analyzedSecurityCount": data["analyzedSecurityCount"],
        "eligibleSecurityCount": data["latestEligibleSecurityCount"],
        "selectedFactor": payload["selectedFactor"],
        "selectedWeightingPolicy": payload["selectedWeightingPolicy"],
        "selectedReason": payload["selectedReason"],
        "selectionDecision": payload["selectionDecision"],
        "gridAccounting": payload["gridAccounting"],
        "policyDiagnostics": payload["policyDiagnostics"],
        "weightingPolicyRegistry": payload["weightingPolicyRegistry"],
        "contributionDiagnostics": payload["contributionDiagnostics"],
        "portfolioPolicy": payload["portfolioPolicy"],
        "backtestHeldPortfolio": payload["backtestHeldPortfolio"],
        "currentTransition": payload["currentTransition"],
        "selectionScore": selected["selection_score"],
        "compositeScore": selected["composite_score"],
        "cagr": selected["cagr"],
        "annualReturn": selected["annual_return"],
        "volatility": selected["volatility"],
        "sharpe": selected["sharpe"],
        "sortino": selected["sortino"],
        "calmar": selected["calmar"],
        "maxDrawdown": selected["max_drawdown"],
        "cvar95": selected["cvar_95"],
        "winRate": selected["win_rate"],
        "annualizedTurnover": selected["annualized_turnover"],
        "annualizedCostDrag": selected["annualized_cost_drag"],
        "observations": selected["observations"],
        "actualExposureObservations": selected["actual_exposure_observations"],
        "valuationCoverageRatio": selected["valuation_coverage_ratio"],
        "dailyRiskObservations": selected["daily_risk_observations"],
        "portfolioStatus": target["status"],
        "portfolioSize": target["selectedSecurityCount"],
        "portfolioEligibleSecurityCount": target["eligibleSecurityCount"],
        "currentResearchTarget": target,
        "cashWeight": target["cashWeight"],
        "maxWeight": payload["config"]["max_weight"],
        "cashReasons": list(target.get("reasons", [])),
        "concentration": target["concentration"],
        "weights": target["weights"],
        "researchOnly": bool(scope.get("researchOnly", True)),
        "notInvestmentRecommendation": bool(scope.get("notInvestmentRecommendation", True)),
        "evidenceStatus": scope.get("evidenceStatus", "same_sample_descriptive"),
        "limitations": list(scope.get("limitations", [])),
        "runtimeSeconds": meta.get("runtimeSeconds"),
        "maxRssBytes": meta.get("maxRssBytes"),
        "page": "momentum-factor-lab",
    }


def dashboard_summary(source: AnalysisResult | dict[str, Any] | Path) -> dict[str, Any]:
    """Return the validated schema-v4 summary without writing site aliases."""

    return _summary(_load_payload(source))


def write_dashboard_site(
    source: AnalysisResult | dict[str, Any] | Path,
    site_dir: Path,
    *,
    title: str = DEFAULT_SITE_TITLE,
) -> dict[str, str]:
    payload = _load_payload(source)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_DASHBOARD_BYTES:
        raise ValueError(
            f"dashboard payload is {len(encoded):,} bytes; limit is {MAX_DASHBOARD_BYTES:,}"
        )
    if not WEB_ROOT.exists():
        raise FileNotFoundError(f"web templates missing: {WEB_ROOT}")
    assets_dir = site_dir / "assets"
    data_dir = site_dir / "data"
    assets_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    css_bytes = (WEB_ROOT / "styles.css").read_bytes()
    js_bytes = (WEB_ROOT / "dashboard.js").read_bytes()
    asset_version = hashlib.sha256(css_bytes + js_bytes).hexdigest()[:12]
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    index = index.replace("__TITLE__", title).replace("__ASSET_VERSION__", asset_version)

    index_path = site_dir / "index.html"
    css_path = assets_dir / "styles.css"
    js_path = assets_dir / "dashboard.js"
    data_path = data_dir / "dashboard.json"
    summary_path = data_dir / "summary.json"
    index_path.write_text(index, encoding="utf-8")
    shutil.copyfile(WEB_ROOT / "styles.css", css_path)
    shutil.copyfile(WEB_ROOT / "dashboard.js", js_path)
    data_path.write_bytes(encoded)
    summary_path.write_text(
        json.dumps(_summary(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "index": str(index_path),
        "css": str(css_path),
        "js": str(js_path),
        "data": str(data_path),
        "summary": str(summary_path),
    }
