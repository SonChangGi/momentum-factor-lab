from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .config import WEIGHTING_POLICIES
from .dashboard import (
    MAX_DASHBOARD_BYTES,
    MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES,
    dashboard_summary,
    externalize_factor_holding_history_sidecar,
    validate_factor_holding_history_sidecar_bytes,
)
from .identity import (
    CANONICAL_JSON_VERSION,
    RESULT_IDENTITY_VERSION,
    canonical_json_bytes,
    canonical_sha256,
)


STATIC_GRID_CONTRACT = "momentum-static-result-grid"
STATIC_GRID_SCHEMA_VERSION = 1
STATIC_GRID_VERSION = "v1"
RESULT_PAYLOAD_SCHEMA_VERSION = 4
MAX_STATIC_GRID_ENTRIES = 64
MIN_ACTUAL_ANALYZED_SECURITY_COUNT = 2_700
STATIC_PRESET_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EXPECTED_TOTAL_FACTOR_COUNT = 64
EXPECTED_INDEPENDENT_FACTOR_COUNT = 61
EXPECTED_ALIAS_FACTOR_COUNT = 3
EXPECTED_POLICY_COUNT = 4
EXPECTED_INDEPENDENT_PAIR_COUNT = 244
EXPECTED_ALIAS_PAIR_COUNT = 12
EXPECTED_TOTAL_PAIR_COUNT = 256

_DETAIL_DIRECTORY = "results"
_SUMMARY_DIRECTORY = "summaries"
_LATEST_DETAIL_ALIAS = "latest.json"
_LATEST_SUMMARY_ALIAS = "latest-summary.json"
_LEGACY_DETAIL_ALIAS = PurePosixPath("../../dashboard.json")
_LEGACY_SUMMARY_ALIAS = PurePosixPath("../../summary.json")


class StaticGridContractError(ValueError):
    """Raised when a static-grid artifact violates the versioned contract."""


class UnsupportedStaticGridInputs(LookupError):
    """Raised when an exact input tuple is not present in the precomputed grid."""


@dataclass(frozen=True)
class StaticGridArtifact:
    detail: Mapping[str, Any]
    summary: Mapping[str, Any]
    preset_id: str | None = None


@dataclass(frozen=True)
class ResolvedStaticGridResult:
    entry: dict[str, Any]
    detail: dict[str, Any]
    summary: dict[str, Any]


def _fail(message: str) -> None:
    raise StaticGridContractError(message)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field} must be an object")
    return dict(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        _fail(f"{field} must be a lowercase SHA-256 digest")
    if any(character not in "0123456789abcdef" for character in value):
        _fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def _validate_preset_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not STATIC_PRESET_ID_PATTERN.fullmatch(value):
        _fail(f"{field} must be a lowercase stable preset identifier")
    return value


def _validate_identity(
    value: object,
    field: str,
    *,
    require_canonical_transport: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = _mapping(value, field)
    if identity.get("identityVersion") != RESULT_IDENTITY_VERSION:
        _fail(f"{field}.identityVersion is unsupported")
    result_key = _validate_sha256(identity.get("resultKey"), f"{field}.resultKey")
    key_parts = _mapping(identity.get("keyParts"), f"{field}.keyParts")
    if key_parts.get("identityVersion") != RESULT_IDENTITY_VERSION:
        _fail(f"{field}.keyParts.identityVersion differs from identityVersion")
    if key_parts.get("canonicalJsonVersion") != CANONICAL_JSON_VERSION:
        _fail(f"{field}.keyParts.canonicalJsonVersion is unsupported")
    if canonical_sha256(key_parts) != result_key:
        _fail(f"{field}.resultKey does not match canonical keyParts")
    canonical_key_parts_json = identity.get("canonicalKeyPartsJson")
    expected_canonical_json = canonical_json_bytes(key_parts).decode("utf-8")
    if require_canonical_transport and not isinstance(canonical_key_parts_json, str):
        _fail(f"{field}.canonicalKeyPartsJson is required")
    if canonical_key_parts_json is not None and canonical_key_parts_json != expected_canonical_json:
        _fail(f"{field}.canonicalKeyPartsJson is not the canonical keyParts encoding")
    normalized_inputs = _mapping(
        key_parts.get("normalizedInputs"),
        f"{field}.keyParts.normalizedInputs",
    )
    return identity, normalized_inputs


def _validate_top_level_result_key(payload: Mapping[str, Any], result_key: str, field: str) -> None:
    top_level = payload.get("resultKey")
    if top_level is not None and top_level != result_key:
        _fail(f"{field}.resultKey differs from resultIdentity.resultKey")


def _validate_actual_market_detail(
    detail: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    if detail.get("schemaVersion") != RESULT_PAYLOAD_SCHEMA_VERSION:
        _fail(f"detail.schemaVersion must be {RESULT_PAYLOAD_SCHEMA_VERSION}")
    data = _mapping(detail.get("data"), "detail.data")
    if data.get("synthetic") is not False or data.get("mode") != "live_market":
        _fail("static-grid detail must be an actual-market, non-synthetic result")
    analyzed_count = data.get("analyzedSecurityCount")
    if not isinstance(analyzed_count, int) or isinstance(analyzed_count, bool):
        _fail("detail.data.analyzedSecurityCount must be an integer")
    if analyzed_count < MIN_ACTUAL_ANALYZED_SECURITY_COUNT:
        _fail(
            "static-grid detail must analyze at least "
            f"{MIN_ACTUAL_ANALYZED_SECURITY_COUNT:,} securities"
        )
    if not isinstance(data.get("asOf"), str) or not data["asOf"]:
        _fail("detail.data.asOf must be a non-empty string")

    key_parts = _mapping(identity.get("keyParts"), "detail.resultIdentity.keyParts")
    market = _mapping(
        key_parts.get("marketSnapshot"), "detail.resultIdentity.keyParts.marketSnapshot"
    )
    parity = {
        "sourceMode": data.get("mode"),
        "dataAsOf": data.get("asOf"),
        "analyzedSecurityCount": analyzed_count,
    }
    for identity_field, observed in parity.items():
        if market.get(identity_field) != observed:
            _fail(f"detail data differs from resultIdentity marketSnapshot at {identity_field}")
    for field in ("selectedFactor", "selectedWeightingPolicy"):
        if not isinstance(detail.get(field), str) or not detail[field]:
            _fail(f"detail.{field} must be a non-empty string")
    return data


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _close(left: object, right: float, *, tolerance: float = 1e-9) -> bool:
    if not _finite_number(left):
        return False
    return math.isclose(float(left), right, rel_tol=tolerance, abs_tol=tolerance)


def _validate_target_allocation(
    detail: Mapping[str, Any],
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], float]:
    target = _mapping(detail.get("currentResearchTarget"), "detail.currentResearchTarget")
    config = _mapping(detail.get("config"), "detail.config")
    max_weight = config.get("max_weight")
    if not _finite_number(max_weight) or not 0.0 < float(max_weight) <= 1.0:
        _fail("detail.config.max_weight must be in (0, 1]")
    max_weight = float(max_weight)

    parity = {
        "factor": detail.get("selectedFactor"),
        "weightingPolicyId": detail.get("selectedWeightingPolicy"),
        "asOf": data.get("asOf"),
        "signalDate": data.get("asOf"),
    }
    for field, expected in parity.items():
        if target.get(field) != expected:
            _fail(f"detail.currentResearchTarget.{field} differs from the selected result")

    weights = target.get("weights")
    if not isinstance(weights, list):
        _fail("detail.currentResearchTarget.weights must be an array")
    selected_count = target.get("selectedSecurityCount")
    if (
        not isinstance(selected_count, int)
        or isinstance(selected_count, bool)
        or selected_count != len(weights)
    ):
        _fail("detail.currentResearchTarget.selectedSecurityCount differs from weights")
    top_n = config.get("top_n")
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1 or len(weights) > top_n:
        _fail("detail.currentResearchTarget holding count exceeds config.top_n")
    eligible_count = target.get("eligibleSecurityCount")
    if (
        not isinstance(eligible_count, int)
        or isinstance(eligible_count, bool)
        or eligible_count < len(weights)
    ):
        _fail("detail.currentResearchTarget.eligibleSecurityCount is inconsistent")

    symbols: set[str] = set()
    values: list[float] = []
    for expected_rank, value in enumerate(weights, start=1):
        row = _mapping(value, f"detail.currentResearchTarget.weights[{expected_rank - 1}]")
        symbol = row.get("symbol")
        normalized_symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
        weight = row.get("weight")
        if (
            row.get("rank") != expected_rank
            or not normalized_symbol
            or normalized_symbol in symbols
            or not _finite_number(row.get("factorScore"))
            or not _finite_number(weight)
            or not 0.0 < float(weight) <= max_weight + 1e-12
        ):
            _fail("detail.currentResearchTarget contains an invalid holding")
        if "maxWeight" in row and not _close(row.get("maxWeight"), max_weight):
            _fail("detail.currentResearchTarget holding maxWeight differs from config")
        symbols.add(normalized_symbol)
        values.append(float(weight))

    cash_weight = target.get("cashWeight")
    if (
        not _finite_number(cash_weight)
        or not 0.0 <= float(cash_weight) <= 1.0
        or not _close(sum(values) + float(cash_weight), 1.0)
    ):
        _fail("detail.currentResearchTarget weights plus cash must equal one")

    concentration = _mapping(
        target.get("concentration"),
        "detail.currentResearchTarget.concentration",
    )
    invested = sum(values)
    normalized = [weight / invested for weight in values] if invested > 0.0 else []
    hhi = sum(weight * weight for weight in normalized)
    ordered = sorted(values, reverse=True)
    expected_concentration = {
        "investedWeight": invested,
        "cashWeight": float(cash_weight),
        "riskySleeveHhi": hhi,
        "effectiveNames": 1.0 / hhi if hhi > 0.0 else 0.0,
        "top1Weight": sum(ordered[:1]),
        "top5Weight": sum(ordered[:5]),
        "maxWeight": ordered[0] if ordered else 0.0,
    }
    for field, expected in expected_concentration.items():
        if not _close(concentration.get(field), expected):
            _fail(f"detail.currentResearchTarget.concentration.{field} is inconsistent")
    return target, max_weight


def _validate_grid_accounting(detail: Mapping[str, Any]) -> dict[str, Any]:
    accounting = _mapping(detail.get("gridAccounting"), "detail.gridAccounting")
    registry = _mapping(
        detail.get("weightingPolicyRegistry"),
        "detail.weightingPolicyRegistry",
    )
    policies = _mapping(
        registry.get("policies"),
        "detail.weightingPolicyRegistry.policies",
    )
    policy_ids = {
        str(policy_id).strip()
        for policy_id in policies
        if isinstance(policy_id, str) and str(policy_id).strip()
    }
    if not policy_ids or len(policy_ids) != len(policies):
        _fail("detail.weightingPolicyRegistry.policies must have unique non-empty ids")
    if policy_ids != set(WEIGHTING_POLICIES) or len(policy_ids) != EXPECTED_POLICY_COUNT:
        _fail("detail.weightingPolicyRegistry must contain the four canonical policies")

    definitions = detail.get("factorDefinitions")
    if not isinstance(definitions, list) or not definitions:
        _fail("detail.factorDefinitions must be a populated array")
    independent_factors: set[str] = set()
    alias_factors: set[str] = set()
    definition_ids: set[str] = set()
    for index, value in enumerate(definitions):
        definition = _mapping(value, f"detail.factorDefinitions[{index}]")
        factor = definition.get("factor")
        if not isinstance(factor, str) or not factor.strip() or factor in definition_ids:
            _fail("detail.factorDefinitions must have unique non-empty factor ids")
        definition_ids.add(factor)
        if definition.get("selection_eligible") is True and not definition.get(
            "compatibility_alias_of"
        ):
            independent_factors.add(factor)
        elif definition.get("selection_eligible") is False and isinstance(
            definition.get("compatibility_alias_of"), str
        ):
            alias_factors.add(factor)
        else:
            _fail("detail.factorDefinitions contains a noncanonical factor classification")
    if (
        len(definition_ids) != EXPECTED_TOTAL_FACTOR_COUNT
        or len(independent_factors) != EXPECTED_INDEPENDENT_FACTOR_COUNT
        or len(alias_factors) != EXPECTED_ALIAS_FACTOR_COUNT
    ):
        _fail("detail.factorDefinitions must contain canonical 64/61/3 factor counts")

    ranking = detail.get("factorPolicyRanking")
    if not isinstance(ranking, list) or not ranking:
        _fail("detail.factorPolicyRanking must be a populated array")
    independent_rows: list[dict[str, Any]] = []
    alias_rows: list[dict[str, Any]] = []
    observed_pairs: set[tuple[str, str]] = set()
    for index, value in enumerate(ranking):
        row = _mapping(value, f"detail.factorPolicyRanking[{index}]")
        factor = row.get("factor")
        if factor not in definition_ids:
            _fail("detail.factorPolicyRanking contains an unknown factor id")
        policy_id = row.get("policy_id")
        if policy_id not in policy_ids:
            _fail("detail.factorPolicyRanking contains an unknown policy id")
        pair = (str(factor), str(policy_id))
        if pair in observed_pairs:
            _fail("detail.factorPolicyRanking contains a duplicate independent pair")
        observed_pairs.add(pair)
        if factor in independent_factors:
            independent_rows.append(row)
        else:
            alias_rows.append(row)

    expected_independent_pairs = {
        (factor, policy_id) for factor in independent_factors for policy_id in policy_ids
    }
    expected_alias_pairs = {
        (factor, policy_id) for factor in alias_factors for policy_id in policy_ids
    }
    expected_pairs = expected_independent_pairs | expected_alias_pairs
    missing_pairs = expected_pairs.difference(observed_pairs)
    unexpected_pairs = observed_pairs.difference(expected_pairs)
    if missing_pairs or unexpected_pairs:
        _fail("detail.factorPolicyRanking canonical 256-row grid is incomplete")
    if (
        len(independent_rows) != EXPECTED_INDEPENDENT_PAIR_COUNT
        or len(alias_rows) != EXPECTED_ALIAS_PAIR_COUNT
        or len(ranking) != EXPECTED_TOTAL_PAIR_COUNT
    ):
        _fail("detail.factorPolicyRanking must contain canonical 244/12/256 row counts")
    for row in alias_rows:
        if row.get("comparison_status") != "duplicate_alias":
            _fail("diagnostic alias factor-policy row must be marked duplicate_alias")

    available_count = 0
    reason_counts: dict[str, int] = {}
    for row in independent_rows:
        status = row.get("comparison_status")
        reason_codes = row.get("exclusion_reason_codes")
        structured_reasons = row.get("exclusion_reasons")
        if status == "available":
            available_count += 1
            if reason_codes != [] or structured_reasons != []:
                _fail("available independent factor-policy row has exclusion reasons")
            continue
        if (
            not isinstance(reason_codes, list)
            or not reason_codes
            or any(not isinstance(code, str) or not code.strip() for code in reason_codes)
            or len(set(reason_codes)) != len(reason_codes)
        ):
            _fail("excluded independent factor-policy row has no exact reason codes")
        if not isinstance(structured_reasons, list) or not structured_reasons:
            _fail("excluded independent factor-policy row has no structured reasons")
        structured_codes: list[str] = []
        for reason_index, value in enumerate(structured_reasons):
            reason = _mapping(
                value,
                f"detail.factorPolicyRanking exclusion_reasons[{reason_index}]",
            )
            code = reason.get("code")
            if not isinstance(code, str) or not code.strip():
                _fail("excluded independent factor-policy structured reason has no code")
            structured_codes.append(code)
        if structured_codes != reason_codes:
            _fail("excluded independent factor-policy reason codes differ from structured reasons")
        for code in reason_codes:
            reason_counts[code] = reason_counts.get(code, 0) + 1

    expected_count = len(expected_independent_pairs)
    evaluated_count = len(independent_rows)
    excluded_count = evaluated_count - available_count
    common_count = sum(
        all(
            row.get("comparison_status") == "available"
            for row in independent_rows
            if row.get("factor") == factor
        )
        for factor in independent_factors
    )
    expected_accounting = {
        "version": 1,
        "independentFactorCount": EXPECTED_INDEPENDENT_FACTOR_COUNT,
        "policyCount": EXPECTED_POLICY_COUNT,
        "expectedIndependentPairCount": expected_count,
        "evaluatedIndependentPairCount": evaluated_count,
        "availableIndependentPairCount": available_count,
        "excludedIndependentPairCount": excluded_count,
        "missingIndependentPairCount": 0,
        "diagnosticAliasFactorCount": EXPECTED_ALIAS_FACTOR_COUNT,
        "diagnosticAliasPairCount": EXPECTED_ALIAS_PAIR_COUNT,
        "commonComparableFactorCount": common_count,
        "exclusionReasonCounts": dict(sorted(reason_counts.items())),
        "invariant": (
            "availableIndependentPairCount + excludedIndependentPairCount = "
            "expectedIndependentPairCount"
        ),
    }
    for field, expected in expected_accounting.items():
        observed = accounting.get(field)
        if isinstance(expected, int):
            valid = (
                isinstance(observed, int)
                and not isinstance(observed, bool)
                and observed == expected
            )
        elif isinstance(expected, Mapping):
            valid = (
                isinstance(observed, Mapping)
                and all(
                    isinstance(code, str)
                    and code.strip()
                    and isinstance(count, int)
                    and not isinstance(count, bool)
                    and count >= 0
                    for code, count in observed.items()
                )
                and dict(observed) == expected
            )
        else:
            valid = observed == expected
        if not valid:
            _fail(f"detail.gridAccounting.{field} is inconsistent with the independent grid")
    if available_count + excluded_count != expected_count:
        _fail("detail.gridAccounting available plus excluded pairs must equal expected pairs")
    return accounting


def _validate_summary_parity(
    detail: Mapping[str, Any],
    summary: Mapping[str, Any],
    identity: Mapping[str, Any],
    data: Mapping[str, Any],
    target: Mapping[str, Any],
    max_weight: float,
    require_canonical_transport: bool,
) -> None:
    if summary.get("schemaVersion") != RESULT_PAYLOAD_SCHEMA_VERSION:
        _fail(f"summary.schemaVersion must be {RESULT_PAYLOAD_SCHEMA_VERSION}")
    summary_identity, _ = _validate_identity(
        summary.get("resultIdentity"),
        "summary.resultIdentity",
        require_canonical_transport=require_canonical_transport,
    )
    if summary_identity != identity:
        _fail("summary.resultIdentity differs from detail.resultIdentity")
    result_key = str(identity["resultKey"])
    _validate_top_level_result_key(summary, result_key, "summary")

    parity = {
        "dataAsOf": data.get("asOf"),
        "dataMode": data.get("mode"),
        "synthetic": False,
        "analyzedSecurityCount": data.get("analyzedSecurityCount"),
        "selectedFactor": detail.get("selectedFactor"),
        "selectedWeightingPolicy": detail.get("selectedWeightingPolicy"),
    }
    for field, expected in parity.items():
        if summary.get(field) != expected:
            _fail(f"summary.{field} differs from detail")
    allocation_parity = {
        "gridAccounting": detail.get("gridAccounting"),
        "currentResearchTarget": target,
        "weights": target.get("weights"),
        "cashWeight": target.get("cashWeight"),
        "maxWeight": max_weight,
        "concentration": target.get("concentration"),
        "portfolioSize": target.get("selectedSecurityCount"),
    }
    for field, expected in allocation_parity.items():
        if summary.get(field) != expected:
            _fail(f"summary.{field} differs from detail.currentResearchTarget")


def _validate_public_research_contract(detail: Mapping[str, Any]) -> None:
    scope = _mapping(detail.get("researchScope"), "detail.researchScope")
    if (
        scope.get("researchOnly") is not True
        or scope.get("notInvestmentRecommendation") is not True
        or scope.get("evidenceStatus") != "same_sample_descriptive_actual_market"
    ):
        _fail("detail.researchScope must declare actual-market research-only evidence")
    limitations = scope.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(value, str) or not value.strip() for value in limitations)
    ):
        _fail("detail.researchScope.limitations must be a populated text array")


def _validate_artifact(
    artifact: StaticGridArtifact,
    *,
    allow_identity_enrichment: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    detail = deepcopy(_mapping(artifact.detail, "detail"))
    summary = deepcopy(_mapping(artifact.summary, "summary"))
    identity, normalized_inputs = _validate_identity(
        detail.get("resultIdentity"),
        "detail.resultIdentity",
        require_canonical_transport=not allow_identity_enrichment,
    )
    result_key = str(identity["resultKey"])
    _validate_top_level_result_key(detail, result_key, "detail")
    data = _validate_actual_market_detail(detail, identity)
    _validate_grid_accounting(detail)
    target, max_weight = _validate_target_allocation(detail, data)
    _validate_public_research_contract(detail)
    _validate_summary_parity(
        detail,
        summary,
        identity,
        data,
        target,
        max_weight,
        not allow_identity_enrichment,
    )
    try:
        canonical_summary = dashboard_summary(detail)
    except (KeyError, TypeError, ValueError) as error:
        _fail(f"detail fails the canonical schema-v4 dashboard contract: {error}")
    if summary != canonical_summary:
        _fail("summary differs from canonical dashboard_summary(detail)")
    if allow_identity_enrichment and "canonicalKeyPartsJson" not in identity:
        identity = {
            **identity,
            "canonicalKeyPartsJson": canonical_json_bytes(identity["keyParts"]).decode("utf-8"),
        }
        detail["resultIdentity"] = deepcopy(identity)
        summary["resultIdentity"] = deepcopy(identity)
    return detail, summary, identity, normalized_inputs


def _artifact_metadata(path: str, encoded: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": _sha256_bytes(encoded),
        "bytes": len(encoded),
    }


def _atomic_write(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _prune_unreferenced_json(directory: Path, referenced_names: set[str]) -> None:
    """Remove content-addressed JSON files not referenced by the new manifest.

    The manifest is the only supported static-grid index.  Retaining artifacts
    from an older engine or identity contract beside the current grid makes it
    too easy to mistake an orphaned URL for a supported preset.  Pruning happens
    only after the replacement manifest has been written atomically.
    """

    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        if path.is_file() and path.name not in referenced_names:
            path.unlink()


def _remove_file_or_symlink(path: Path) -> None:
    if path.is_file() or path.is_symlink():
        path.unlink()


def _grid_root(data_dir: Path) -> Path:
    return data_dir / "grid" / STATIC_GRID_VERSION


def write_static_grid(
    data_dir: Path,
    artifacts: Iterable[StaticGridArtifact],
    *,
    default_result_key: str,
    write_default_aliases: bool = False,
    max_entries: int = MAX_STATIC_GRID_ENTRIES,
) -> dict[str, Path]:
    """Write a bounded, sparse grid after validating every result as a unit.

    ``data_dir`` is the public site's data directory. Content-addressed files and
    the manifest are written below ``grid/v1``. Optional aliases are byte-for-byte
    copies of the declared default result; callers cannot supply separate alias
    payloads.
    """

    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
        _fail("max_entries must be a positive integer")
    if max_entries > MAX_STATIC_GRID_ENTRIES:
        _fail(f"max_entries cannot exceed {MAX_STATIC_GRID_ENTRIES}")
    _validate_sha256(default_result_key, "default_result_key")

    prepared: list[dict[str, Any]] = []
    seen_result_keys: set[str] = set()
    seen_input_tuples: dict[bytes, str] = {}
    seen_preset_ids: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, StaticGridArtifact):
            _fail("artifacts must contain StaticGridArtifact values")
        detail, summary, identity, normalized_inputs = _validate_artifact(
            artifact,
            allow_identity_enrichment=True,
        )
        detail, sidecar_bytes = externalize_factor_holding_history_sidecar(detail)
        if sidecar_bytes is None:
            _fail("static-grid detail has no embedded factor holding history sidecar")
        if len(sidecar_bytes) > MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES:
            _fail(
                "factor holding history sidecar is "
                f"{len(sidecar_bytes):,} bytes; limit is "
                f"{MAX_FACTOR_HOLDING_HISTORY_SIDECAR_BYTES:,}"
            )
        dashboard_summary(detail)
        result_key = str(identity["resultKey"])
        if result_key in seen_result_keys:
            _fail(f"duplicate resultKey in static grid: {result_key}")
        input_tuple = canonical_json_bytes(normalized_inputs)
        if input_tuple in seen_input_tuples:
            _fail(
                "duplicate normalized input tuple in static grid: "
                f"{seen_input_tuples[input_tuple]} and {result_key}"
            )
        seen_result_keys.add(result_key)
        seen_input_tuples[input_tuple] = result_key
        preset_id = None
        if artifact.preset_id is not None:
            preset_id = _validate_preset_id(artifact.preset_id, "artifact.preset_id")
            if preset_id in seen_preset_ids:
                _fail(f"duplicate presetId in static grid: {preset_id}")
            seen_preset_ids.add(preset_id)
        detail_bytes = canonical_json_bytes(detail)
        summary_bytes = canonical_json_bytes(summary)
        if len(detail_bytes) > MAX_DASHBOARD_BYTES:
            _fail(
                f"detail payload is {len(detail_bytes):,} bytes; limit is {MAX_DASHBOARD_BYTES:,}"
            )
        detail_path = f"{_DETAIL_DIRECTORY}/{result_key}.json"
        summary_path = f"{_SUMMARY_DIRECTORY}/{result_key}.json"
        prepared.append(
            {
                "resultKey": result_key,
                "presetId": preset_id,
                "normalizedInputs": normalized_inputs,
                "identity": identity,
                "detail": _artifact_metadata(detail_path, detail_bytes),
                "summary": _artifact_metadata(summary_path, summary_bytes),
                "detailBytes": detail_bytes,
                "summaryBytes": summary_bytes,
                "sidecarBytes": sidecar_bytes,
                "sidecarPath": detail["factorHoldingHistorySidecar"]["path"],
            }
        )

    if not prepared:
        _fail("static grid must contain at least one result")
    declared_preset_count = sum(item["presetId"] is not None for item in prepared)
    if declared_preset_count not in {0, len(prepared)}:
        _fail("static grid presetId metadata must be declared for every entry or none")
    if len(prepared) > max_entries:
        _fail(f"static grid has {len(prepared)} entries; maximum is {max_entries}")
    if default_result_key not in seen_result_keys:
        _fail("default_result_key is not present in the static grid")

    prepared.sort(key=lambda item: str(item["resultKey"]))
    grid_root = _grid_root(data_dir)
    manifest_entries: list[dict[str, Any]] = []
    default_item: dict[str, Any] | None = None
    written: dict[str, Path] = {}
    for item in prepared:
        result_key = str(item["resultKey"])
        detail_path = grid_root / str(item["detail"]["path"])
        summary_path = grid_root / str(item["summary"]["path"])
        _atomic_write(detail_path, item["detailBytes"])
        _atomic_write(summary_path, item["summaryBytes"])
        sidecar_relative = PurePosixPath(str(item["sidecarPath"]))
        sidecar_path = data_dir.parent.joinpath(*sidecar_relative.parts)
        _atomic_write(sidecar_path, item["sidecarBytes"])
        written[f"detail:{result_key}"] = detail_path
        written[f"summary:{result_key}"] = summary_path
        written[f"factorHoldingHistory:{result_key}"] = sidecar_path
        manifest_entry = {
            "normalizedInputs": item["normalizedInputs"],
            "resultKey": result_key,
            "identity": item["identity"],
            "detail": item["detail"],
            "summary": item["summary"],
        }
        if item["presetId"] is not None:
            manifest_entry["presetId"] = item["presetId"]
        manifest_entries.append(manifest_entry)
        if result_key == default_result_key:
            default_item = item
    if default_item is None:  # pragma: no cover - guarded above
        _fail("default result disappeared while writing the static grid")

    manifest: dict[str, Any] = {
        "schemaVersion": STATIC_GRID_SCHEMA_VERSION,
        "contract": STATIC_GRID_CONTRACT,
        "gridVersion": STATIC_GRID_VERSION,
        "bounded": True,
        "maxEntries": max_entries,
        "entryCount": len(manifest_entries),
        "defaultResultKey": default_result_key,
        "entries": manifest_entries,
    }
    if write_default_aliases:
        alias_specs = {
            "latestDetail": (_LATEST_DETAIL_ALIAS, default_item["detailBytes"]),
            "latestSummary": (_LATEST_SUMMARY_ALIAS, default_item["summaryBytes"]),
            "legacyDetail": (str(_LEGACY_DETAIL_ALIAS), default_item["detailBytes"]),
            "legacySummary": (str(_LEGACY_SUMMARY_ALIAS), default_item["summaryBytes"]),
        }
        aliases: dict[str, dict[str, object]] = {}
        for name, (relative_path, encoded) in alias_specs.items():
            alias_path = grid_root / relative_path
            _atomic_write(alias_path, encoded)
            aliases[name] = _artifact_metadata(relative_path, encoded)
            written[f"alias:{name}"] = alias_path
        manifest["defaultAliases"] = {
            "resultKey": default_result_key,
            "artifacts": aliases,
        }

    manifest_path = grid_root / "manifest.json"
    _atomic_write(manifest_path, canonical_json_bytes(manifest))
    _prune_unreferenced_json(
        data_dir / "factor-holding-history",
        {f"{item['resultKey']}.json" for item in prepared},
    )
    if not write_default_aliases:
        for relative_path in (
            _LATEST_DETAIL_ALIAS,
            _LATEST_SUMMARY_ALIAS,
            str(_LEGACY_DETAIL_ALIAS),
            str(_LEGACY_SUMMARY_ALIAS),
        ):
            _remove_file_or_symlink(grid_root / relative_path)
    _prune_unreferenced_json(
        grid_root / _DETAIL_DIRECTORY,
        {f"{item['resultKey']}.json" for item in prepared},
    )
    _prune_unreferenced_json(
        grid_root / _SUMMARY_DIRECTORY,
        {f"{item['resultKey']}.json" for item in prepared},
    )
    written["manifest"] = manifest_path
    validate_static_grid(manifest_path)
    return written


def _validate_artifact_reference(value: object, field: str, expected_path: str) -> dict[str, Any]:
    reference = _mapping(value, field)
    if reference.get("path") != expected_path:
        _fail(f"{field}.path must be {expected_path}")
    _validate_sha256(reference.get("sha256"), f"{field}.sha256")
    byte_count = reference.get("bytes")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 1:
        _fail(f"{field}.bytes must be a positive integer")
    return reference


def validate_manifest(
    value: object,
    *,
    max_entries: int = MAX_STATIC_GRID_ENTRIES,
) -> dict[str, Any]:
    manifest = _mapping(value, "manifest")
    if manifest.get("schemaVersion") != STATIC_GRID_SCHEMA_VERSION:
        _fail(f"manifest.schemaVersion must be {STATIC_GRID_SCHEMA_VERSION}")
    if manifest.get("contract") != STATIC_GRID_CONTRACT:
        _fail(f"manifest.contract must be {STATIC_GRID_CONTRACT}")
    if manifest.get("gridVersion") != STATIC_GRID_VERSION:
        _fail(f"manifest.gridVersion must be {STATIC_GRID_VERSION}")
    if manifest.get("bounded") is not True:
        _fail("manifest.bounded must be true")
    declared_max = manifest.get("maxEntries")
    if not isinstance(declared_max, int) or isinstance(declared_max, bool):
        _fail("manifest.maxEntries must be an integer")
    if declared_max < 1 or declared_max > max_entries or declared_max > MAX_STATIC_GRID_ENTRIES:
        _fail("manifest.maxEntries exceeds the supported bound")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        _fail("manifest.entries must be a non-empty array")
    if len(entries) > declared_max:
        _fail("manifest entry count exceeds manifest.maxEntries")
    if manifest.get("entryCount") != len(entries):
        _fail("manifest.entryCount differs from entries length")

    default_result_key = _validate_sha256(
        manifest.get("defaultResultKey"),
        "manifest.defaultResultKey",
    )
    seen_result_keys: set[str] = set()
    seen_input_tuples: set[bytes] = set()
    seen_preset_ids: set[str] = set()
    declared_preset_count = 0
    for index, raw_entry in enumerate(entries):
        field = f"manifest.entries[{index}]"
        entry = _mapping(raw_entry, field)
        result_key = _validate_sha256(entry.get("resultKey"), f"{field}.resultKey")
        if result_key in seen_result_keys:
            _fail(f"duplicate resultKey in manifest: {result_key}")
        seen_result_keys.add(result_key)
        identity, identity_inputs = _validate_identity(
            entry.get("identity"),
            f"{field}.identity",
            require_canonical_transport=True,
        )
        if identity["resultKey"] != result_key:
            _fail(f"{field}.identity.resultKey differs from entry resultKey")
        normalized_inputs = _mapping(entry.get("normalizedInputs"), f"{field}.normalizedInputs")
        if normalized_inputs != identity_inputs:
            _fail(f"{field}.normalizedInputs differs from identity")
        input_tuple = canonical_json_bytes(normalized_inputs)
        if input_tuple in seen_input_tuples:
            _fail("duplicate normalized input tuple in manifest")
        seen_input_tuples.add(input_tuple)
        if "presetId" in entry:
            preset_id = _validate_preset_id(entry.get("presetId"), f"{field}.presetId")
            if preset_id in seen_preset_ids:
                _fail(f"duplicate presetId in manifest: {preset_id}")
            seen_preset_ids.add(preset_id)
            declared_preset_count += 1
        _validate_artifact_reference(
            entry.get("detail"),
            f"{field}.detail",
            f"{_DETAIL_DIRECTORY}/{result_key}.json",
        )
        _validate_artifact_reference(
            entry.get("summary"),
            f"{field}.summary",
            f"{_SUMMARY_DIRECTORY}/{result_key}.json",
        )
    if declared_preset_count not in {0, len(entries)}:
        _fail("manifest presetId metadata must be declared for every entry or none")
    if default_result_key not in seen_result_keys:
        _fail("manifest.defaultResultKey does not identify an entry")

    default_aliases = manifest.get("defaultAliases")
    if default_aliases is not None:
        aliases = _mapping(default_aliases, "manifest.defaultAliases")
        if aliases.get("resultKey") != default_result_key:
            _fail("manifest.defaultAliases.resultKey differs from defaultResultKey")
        artifacts = _mapping(aliases.get("artifacts"), "manifest.defaultAliases.artifacts")
        expected = {
            "latestDetail": _LATEST_DETAIL_ALIAS,
            "latestSummary": _LATEST_SUMMARY_ALIAS,
            "legacyDetail": str(_LEGACY_DETAIL_ALIAS),
            "legacySummary": str(_LEGACY_SUMMARY_ALIAS),
        }
        if set(artifacts) != set(expected):
            _fail("manifest.defaultAliases.artifacts must contain only the fixed aliases")
        for name, expected_path in expected.items():
            _validate_artifact_reference(
                artifacts[name],
                f"manifest.defaultAliases.artifacts.{name}",
                expected_path,
            )
    return deepcopy(manifest)


def _read_json_bytes(path: Path, field: str) -> tuple[bytes, dict[str, Any]]:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        _fail(f"{field} is missing or unreadable: {error}")
    try:
        value = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{field} is not valid UTF-8 JSON: {error}")
    return encoded, _mapping(value, field)


def _verify_reference(root: Path, reference: Mapping[str, Any], field: str) -> bytes:
    relative = PurePosixPath(str(reference["path"]))
    if relative.is_absolute():
        _fail(f"{field}.path must be relative")
    path = root.joinpath(*relative.parts)
    try:
        encoded = path.read_bytes()
    except OSError as error:
        _fail(f"{field} is missing or unreadable: {error}")
    if len(encoded) != reference["bytes"]:
        _fail(f"{field} byte count differs from manifest")
    if _sha256_bytes(encoded) != reference["sha256"]:
        _fail(f"{field} SHA-256 differs from manifest")
    return encoded


def validate_static_grid(
    manifest_path: Path,
    *,
    max_entries: int = MAX_STATIC_GRID_ENTRIES,
) -> dict[str, Any]:
    if (
        manifest_path.name != "manifest.json"
        or manifest_path.parent.name != STATIC_GRID_VERSION
        or manifest_path.parent.parent.name != "grid"
    ):
        _fail("manifest path must use the data/grid/v1/manifest.json layout")
    manifest_bytes, raw_manifest = _read_json_bytes(manifest_path, "manifest")
    if not manifest_bytes:
        _fail("manifest is empty")
    manifest = validate_manifest(raw_manifest, max_entries=max_entries)
    grid_root = manifest_path.parent
    loaded_by_key: dict[str, tuple[bytes, bytes]] = {}
    for index, entry in enumerate(manifest["entries"]):
        result_key = str(entry["resultKey"])
        detail_bytes = _verify_reference(
            grid_root,
            entry["detail"],
            f"manifest.entries[{index}].detail",
        )
        summary_bytes = _verify_reference(
            grid_root,
            entry["summary"],
            f"manifest.entries[{index}].summary",
        )
        detail = _mapping(json.loads(detail_bytes), f"detail[{result_key}]")
        summary = _mapping(json.loads(summary_bytes), f"summary[{result_key}]")
        validated_detail, validated_summary, identity, normalized_inputs = _validate_artifact(
            StaticGridArtifact(detail=detail, summary=summary),
            allow_identity_enrichment=False,
        )
        if identity != entry["identity"]:
            _fail(f"artifact identity differs from manifest for {result_key}")
        if normalized_inputs != entry["normalizedInputs"]:
            _fail(f"artifact normalized inputs differ from manifest for {result_key}")
        if validated_detail != detail or validated_summary != summary:  # pragma: no cover
            _fail(f"artifact changed during validation for {result_key}")
        sidecar_reference = _mapping(
            detail.get("factorHoldingHistorySidecar"),
            f"detail[{result_key}].factorHoldingHistorySidecar",
        )
        sidecar_relative = PurePosixPath(str(sidecar_reference.get("path")))
        sidecar_path = grid_root.parents[2].joinpath(*sidecar_relative.parts)
        try:
            sidecar_bytes = sidecar_path.read_bytes()
            validate_factor_holding_history_sidecar_bytes(detail, sidecar_bytes)
        except (OSError, TypeError, ValueError) as error:
            _fail(f"factor holding history sidecar is invalid for {result_key}: {error}")
        loaded_by_key[result_key] = (detail_bytes, summary_bytes)

    aliases = manifest.get("defaultAliases")
    if aliases is not None:
        default_detail, default_summary = loaded_by_key[manifest["defaultResultKey"]]
        for name, reference in aliases["artifacts"].items():
            encoded = _verify_reference(
                grid_root,
                reference,
                f"manifest.defaultAliases.artifacts.{name}",
            )
            expected = default_summary if "Summary" in name else default_detail
            if encoded != expected:
                _fail(f"default alias {name} is not a byte-for-byte copy of the default result")
    return manifest


def resolve_exact_inputs(
    manifest: Mapping[str, Any],
    normalized_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve only a complete, exactly equal precomputed input tuple."""

    validated = validate_manifest(manifest)
    requested = _mapping(normalized_inputs, "normalized_inputs")
    requested_tuple = canonical_json_bytes(requested)
    matches = [
        entry
        for entry in validated["entries"]
        if canonical_json_bytes(entry["normalizedInputs"]) == requested_tuple
    ]
    if not matches:
        raise UnsupportedStaticGridInputs(
            "the exact normalized input tuple is not precomputed in this static grid; "
            "run the local backend/API for arbitrary inputs"
        )
    if len(matches) != 1:  # pragma: no cover - validate_manifest rejects duplicates
        _fail("exact input tuple resolved to multiple static-grid entries")
    return deepcopy(matches[0])


def load_resolved_static_result(
    manifest_path: Path,
    normalized_inputs: Mapping[str, Any],
) -> ResolvedStaticGridResult:
    manifest = validate_static_grid(manifest_path)
    entry = resolve_exact_inputs(manifest, normalized_inputs)
    grid_root = manifest_path.parent
    _, detail = _read_json_bytes(
        grid_root / str(entry["detail"]["path"]),
        "resolved detail",
    )
    _, summary = _read_json_bytes(
        grid_root / str(entry["summary"]["path"]),
        "resolved summary",
    )
    return ResolvedStaticGridResult(entry=entry, detail=detail, summary=summary)
