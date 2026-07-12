from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from momentum_factor_lab.config import WEIGHTING_POLICIES
from momentum_factor_lab.data import canonical_records_sha256
from momentum_factor_lab.dashboard import MAX_DASHBOARD_BYTES, dashboard_summary
from momentum_factor_lab.identity import (
    canonical_json_bytes,
    canonical_sha256,
)
from momentum_factor_lab.static_grid import (
    MAX_STATIC_GRID_ENTRIES,
    STATIC_GRID_CONTRACT,
    STATIC_GRID_VERSION,
    StaticGridArtifact,
    StaticGridContractError,
    UnsupportedStaticGridInputs,
    load_resolved_static_result,
    resolve_exact_inputs,
    validate_manifest,
    validate_static_grid,
    write_static_grid,
)
from momentum_factor_lab.workflow import AnalysisResult, result_payload


ROOT = Path(__file__).resolve().parents[1]


def _actual_market_detail(source: AnalysisResult) -> dict[str, object]:
    detail = result_payload(source)
    analyzed_count = 2_861
    data = detail["data"]
    price_sources = [
        {
            "symbol": f"FIX{index:04d}",
            "price_source": "fixture-provider",
            "adjustment_note": "canonical actual-market fixture",
        }
        for index in range(analyzed_count)
    ]
    source_health = [
        {
            "source": "fixture-provider",
            "status": "ok",
            "records": int(data["observations"]),
            "cache_hit": False,
        }
    ]
    hashes = {
        "prices": "c" * 64,
        "volumes": "d" * 64,
        "dollarVolumes": "e" * 64,
        "rawCloses": "f" * 64,
        "requestedSymbols": "1" * 64,
        "returnedSymbols": "2" * 64,
        "universeRecords": "3" * 64,
        "priceSources": canonical_records_sha256(price_sources),
        "dataSources": canonical_records_sha256(source_health),
    }
    data.update(
        {
            "mode": "live_market",
            "synthetic": False,
            "sourceLabel": "fixture actual-market provider",
            "provider": "fixture-provider",
            "priceBasis": "provider_adjusted_close",
            "volumeBasis": "raw_close_x_raw_volume",
            "rawCloseProxySymbolCount": 0,
            "inputSha256": hashes,
            "requestedCandidateCount": analyzed_count,
            "providerReturnedCandidateCount": analyzed_count,
            "inputSecurityCount": analyzed_count,
            "analyzedSecurityCount": analyzed_count,
            "analyzedSymbols": [row["symbol"] for row in price_sources],
            "rawCloseAvailable": True,
        }
    )
    data["funnel"].update(
        {
            "requestedCandidateCount": analyzed_count,
            "providerUsableCandidateCount": analyzed_count,
            "analyzedSecurityCount": analyzed_count,
        }
    )
    detail["config"]["data_mode"] = "live_market"
    detail["researchScope"]["evidenceStatus"] = "same_sample_descriptive_actual_market"
    detail["priceSources"] = price_sources
    detail["sourceHealth"] = source_health

    identity = detail["resultIdentity"]
    key_parts = identity["keyParts"]
    normalized = key_parts["normalizedInputs"]
    normalized.update({"data_mode": "live_market", "demo": False, "live": True})
    key_parts["marketSnapshot"].update(
        {
            "sourceMode": data["mode"],
            "sourceLabel": data["sourceLabel"],
            "provider": data["provider"],
            "priceBasis": data["priceBasis"],
            "volumeBasis": data["volumeBasis"],
            "rawCloseProxySymbolCount": data["rawCloseProxySymbolCount"],
            "requestedThrough": data["requestedThrough"],
            "dataAsOf": data["asOf"],
            "inputSha256": hashes,
            "requestedCandidateCount": analyzed_count,
            "providerReturnedCandidateCount": analyzed_count,
            "analyzedSecurityCount": analyzed_count,
            "candidateSymbolsSha256": canonical_sha256(data["analyzedSymbols"]),
        }
    )
    result_key = canonical_sha256(key_parts)
    identity["resultKey"] = result_key
    identity["canonicalKeyPartsJson"] = canonical_json_bytes(key_parts).decode("utf-8")
    detail["resultKey"] = result_key
    return detail


@pytest.fixture(scope="session")
def canonical_actual_artifact(demo_result: AnalysisResult) -> StaticGridArtifact:
    detail = _actual_market_detail(demo_result)
    return StaticGridArtifact(detail=detail, summary=dashboard_summary(detail))


def _refresh_detail_identity(detail: dict[str, object]) -> None:
    identity = detail["resultIdentity"]
    key_parts = identity["keyParts"]
    result_key = canonical_sha256(key_parts)
    identity["resultKey"] = result_key
    identity["canonicalKeyPartsJson"] = canonical_json_bytes(key_parts).decode("utf-8")
    detail["resultKey"] = result_key


def _artifact(
    base: StaticGridArtifact,
    *,
    top_n: int = 20,
    market_variant: str | None = None,
    preset_id: str | None = None,
) -> StaticGridArtifact:
    detail = deepcopy(base.detail)
    detail["config"]["top_n"] = top_n
    detail["researchInputs"]["topN"] = top_n
    detail["portfolioPolicy"]["parameters"]["topN"] = top_n
    identity = detail["resultIdentity"]
    key_parts = identity["keyParts"]
    key_parts["normalizedInputs"]["top_n"] = top_n
    if market_variant is not None:
        price_digest = canonical_sha256({"marketVariant": market_variant})
        detail["data"]["inputSha256"]["prices"] = price_digest
        key_parts["marketSnapshot"]["inputSha256"]["prices"] = price_digest
    _refresh_detail_identity(detail)
    summary = dashboard_summary(detail)
    return StaticGridArtifact(detail=detail, summary=summary, preset_id=preset_id)


def _remove_price_sources_hash(artifact: StaticGridArtifact) -> None:
    artifact.detail["data"]["inputSha256"].pop("priceSources")
    artifact.detail["resultIdentity"]["keyParts"]["marketSnapshot"]["inputSha256"].pop(
        "priceSources", None
    )
    _refresh_detail_identity(artifact.detail)
    artifact.summary["resultKey"] = artifact.detail["resultKey"]
    artifact.summary["resultIdentity"] = deepcopy(artifact.detail["resultIdentity"])


def _result_key(artifact: StaticGridArtifact) -> str:
    return str(artifact.detail["resultIdentity"]["resultKey"])


def test_writes_sparse_content_addressed_grid_and_default_aliases(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    first = _artifact(canonical_actual_artifact, top_n=20)
    second = _artifact(canonical_actual_artifact, top_n=35)
    default_key = _result_key(second)

    written = write_static_grid(
        tmp_path / "data",
        [first, second],
        default_result_key=default_key,
        write_default_aliases=True,
    )
    manifest_path = written["manifest"]
    manifest = validate_static_grid(manifest_path)

    assert manifest["contract"] == STATIC_GRID_CONTRACT
    assert manifest["gridVersion"] == STATIC_GRID_VERSION
    assert manifest["bounded"] is True
    assert manifest["entryCount"] == 2
    assert manifest["defaultResultKey"] == default_key
    assert {entry["resultKey"] for entry in manifest["entries"]} == {
        _result_key(first),
        _result_key(second),
    }

    for entry in manifest["entries"]:
        assert entry["normalizedInputs"] == entry["identity"]["keyParts"]["normalizedInputs"]
        assert entry["resultKey"] == entry["identity"]["resultKey"]
        for kind in ("detail", "summary"):
            path = manifest_path.parent / entry[kind]["path"]
            encoded = path.read_bytes()
            assert entry[kind]["bytes"] == len(encoded)
            assert entry[kind]["sha256"] == hashlib.sha256(encoded).hexdigest()

    default_entry = next(
        entry for entry in manifest["entries"] if entry["resultKey"] == default_key
    )
    default_detail = (manifest_path.parent / default_entry["detail"]["path"]).read_bytes()
    default_summary = (manifest_path.parent / default_entry["summary"]["path"]).read_bytes()
    assert (manifest_path.parent / "latest.json").read_bytes() == default_detail
    assert (manifest_path.parent / "latest-summary.json").read_bytes() == default_summary
    assert (tmp_path / "data" / "dashboard.json").read_bytes() == default_detail
    assert (tmp_path / "data" / "summary.json").read_bytes() == default_summary


def test_writes_unique_stable_preset_ids_for_result_key_rotation(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    first = _artifact(canonical_actual_artifact, top_n=20, preset_id="latest-top20")
    second = _artifact(
        canonical_actual_artifact,
        top_n=35,
        preset_id="latest-top35",
    )

    manifest_path = write_static_grid(
        tmp_path / "data",
        [first, second],
        default_result_key=_result_key(first),
    )["manifest"]
    manifest = validate_static_grid(manifest_path)

    assert {entry["presetId"] for entry in manifest["entries"]} == {
        "latest-top20",
        "latest-top35",
    }


@pytest.mark.parametrize(
    ("artifact_specs", "message"),
    [
        (
            [{"top_n": 20, "preset_id": "latest"}, {"top_n": 35}],
            "every entry or none",
        ),
        (
            [
                {"top_n": 20, "preset_id": "latest"},
                {"top_n": 35, "preset_id": "latest"},
            ],
            "duplicate presetId",
        ),
        ([{"preset_id": "Latest Top20"}], "lowercase stable"),
    ],
)
def test_rejects_partial_duplicate_or_invalid_preset_ids(
    artifact_specs: list[dict[str, object]],
    message: str,
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifacts = [
        _artifact(canonical_actual_artifact, **artifact_spec) for artifact_spec in artifact_specs
    ]
    with pytest.raises(StaticGridContractError, match=message):
        write_static_grid(
            tmp_path / "data",
            artifacts,
            default_result_key=_result_key(artifacts[0]),
        )


def test_rewriting_grid_prunes_content_addressed_artifacts_not_in_new_manifest(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    first = _artifact(canonical_actual_artifact, top_n=20)
    second = _artifact(canonical_actual_artifact, top_n=35)
    first_key = _result_key(first)
    second_key = _result_key(second)
    data_dir = tmp_path / "data"

    write_static_grid(
        data_dir,
        [first, second],
        default_result_key=first_key,
    )
    grid_root = data_dir / "grid" / "v1"
    assert (grid_root / "results" / f"{second_key}.json").is_file()
    assert (grid_root / "summaries" / f"{second_key}.json").is_file()

    write_static_grid(
        data_dir,
        [first],
        default_result_key=first_key,
    )

    assert (grid_root / "results" / f"{first_key}.json").is_file()
    assert (grid_root / "summaries" / f"{first_key}.json").is_file()
    assert not (grid_root / "results" / f"{second_key}.json").exists()
    assert not (grid_root / "summaries" / f"{second_key}.json").exists()


def test_rewriting_without_default_aliases_removes_previous_public_aliases(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    result_key = _result_key(artifact)
    data_dir = tmp_path / "data"
    grid_root = data_dir / "grid" / "v1"
    aliases = (
        grid_root / "latest.json",
        grid_root / "latest-summary.json",
        data_dir / "dashboard.json",
        data_dir / "summary.json",
    )

    write_static_grid(
        data_dir,
        [artifact],
        default_result_key=result_key,
        write_default_aliases=True,
    )
    assert all(path.is_file() for path in aliases)

    manifest_path = write_static_grid(
        data_dir,
        [artifact],
        default_result_key=result_key,
        write_default_aliases=False,
    )["manifest"]
    manifest = validate_static_grid(manifest_path)

    assert "defaultAliases" not in manifest
    assert all(not path.exists() and not path.is_symlink() for path in aliases)


def test_exact_tuple_resolution_has_no_partial_or_nearest_fallback(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact, top_n=20)
    manifest_path = write_static_grid(
        tmp_path / "data",
        [artifact],
        default_result_key=_result_key(artifact),
    )["manifest"]
    manifest = validate_static_grid(manifest_path)
    exact_inputs = artifact.detail["resultIdentity"]["keyParts"]["normalizedInputs"]

    entry = resolve_exact_inputs(manifest, exact_inputs)
    resolved = load_resolved_static_result(manifest_path, exact_inputs)

    assert entry["resultKey"] == _result_key(artifact)
    assert resolved.entry == entry
    assert resolved.detail == artifact.detail
    assert resolved.summary == artifact.summary
    with pytest.raises(UnsupportedStaticGridInputs, match="local backend/API"):
        resolve_exact_inputs(manifest, {"top_n": 20})
    with pytest.raises(UnsupportedStaticGridInputs, match="local backend/API"):
        resolve_exact_inputs(manifest, {**exact_inputs, "top_n": 21})


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda artifact: artifact.detail["data"].update({"synthetic": True, "mode": "demo"}),
            "actual-market, non-synthetic",
        ),
        (
            lambda artifact: artifact.detail["data"].update(
                {"synthetic": False, "mode": "local_file"}
            ),
            "actual-market, non-synthetic",
        ),
        (
            lambda artifact: artifact.detail["data"].update({"analyzedSecurityCount": 2_699}),
            "at least 2,700 securities",
        ),
        (
            lambda artifact: artifact.summary.update({"selectedFactor": "different"}),
            "summary.selectedFactor differs",
        ),
        (
            lambda artifact: artifact.summary.update({"weights": [], "cashWeight": 1.0}),
            "summary.weights differs",
        ),
        (
            lambda artifact: artifact.detail["currentResearchTarget"]["weights"][0].update(
                {"weight": -0.25}
            ),
            "invalid holding",
        ),
        (
            lambda artifact: artifact.summary.update({"resultIdentity": {}}),
            "identityVersion is unsupported",
        ),
        (
            lambda artifact: artifact.detail.update({"resultKey": "f" * 64}),
            "differs from resultIdentity.resultKey",
        ),
    ],
)
def test_rejects_non_actual_or_non_parity_payloads(
    mutator,
    message: str,
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    mutator(artifact)

    with pytest.raises(StaticGridContractError, match=message):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("researchScope", "researchScope must be an object"),
        ("selectionMethod", "canonical schema-v4 dashboard contract"),
        ("currentTransition", "canonical schema-v4 dashboard contract"),
        ("priceSources", "provider provenance contract is incomplete"),
        ("sourceHealth", "provider provenance contract is incomplete"),
    ],
)
def test_rejects_partial_payload_missing_browser_or_quant_contract(
    field: str,
    message: str,
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    del artifact.detail[field]

    with pytest.raises(StaticGridContractError, match=message):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_one_factor_one_policy_partial_schema_v4_payload(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    detail = artifact.detail
    selected_factor = detail["selectedFactor"]
    selected_policy = detail["selectedWeightingPolicy"]
    detail["factorDefinitions"] = [
        next(
            definition
            for definition in detail["factorDefinitions"]
            if definition["factor"] == selected_factor
        )
    ]
    detail["weightingPolicyRegistry"]["policies"] = {
        selected_policy: detail["weightingPolicyRegistry"]["policies"][selected_policy]
    }
    detail["factorPolicyRanking"] = [
        next(
            row
            for row in detail["factorPolicyRanking"]
            if row["factor"] == selected_factor and row["policy_id"] == selected_policy
        )
    ]

    with pytest.raises(StaticGridContractError, match="four canonical policies"):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda artifact: artifact.detail["researchScope"].update({"researchOnly": False}),
            "actual-market research-only evidence",
        ),
        (
            _remove_price_sources_hash,
            "input snapshot hash contract is incomplete",
        ),
        (
            lambda artifact: artifact.detail["priceSources"].__setitem__(
                1, deepcopy(artifact.detail["priceSources"][0])
            ),
            "priceSources rows are invalid or duplicated",
        ),
        (
            lambda artifact: artifact.detail.update(
                {"priceSources": artifact.detail["priceSources"][:-1]}
            ),
            "priceSources do not cover the analyzed universe",
        ),
        (
            lambda artifact: artifact.detail["sourceHealth"][0].update({"status": ""}),
            "sourceHealth source/status rows are invalid",
        ),
    ],
)
def test_rejects_incomplete_or_ambiguous_public_provenance(
    mutator,
    message: str,
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    mutator(artifact)

    with pytest.raises(StaticGridContractError, match=message):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_summary_that_is_not_exact_canonical_generated_summary(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    artifact.summary["researchOnly"] = False

    with pytest.raises(
        StaticGridContractError,
        match=r"summary differs from canonical dashboard_summary\(detail\)",
    ):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_detail_larger_than_dashboard_publication_limit(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    artifact.detail["publicationPadding"] = "x" * MAX_DASHBOARD_BYTES
    assert len(canonical_json_bytes(artifact.detail)) > MAX_DASHBOARD_BYTES

    with pytest.raises(
        StaticGridContractError,
        match=rf"detail payload is .* bytes; limit is {MAX_DASHBOARD_BYTES:,}",
    ):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def _add_excluded_independent_pair(artifact: StaticGridArtifact) -> None:
    detail = artifact.detail
    summary = artifact.summary
    excluded_factor = next(
        definition["factor"]
        for definition in detail["factorDefinitions"]
        if definition.get("selection_eligible") is True
        and definition["factor"] != detail["selectedFactor"]
    )
    row = next(
        row
        for row in detail["factorPolicyRanking"]
        if row["factor"] == excluded_factor and row["policy_id"] == WEIGHTING_POLICIES[0]
    )
    row.update(
        {
            "comparison_status": "insufficient_history",
            "exclusion_reason_codes": ["insufficient_observations"],
            "exclusion_reasons": [
                {
                    "code": "insufficient_observations",
                    "observed": 100,
                    "required": 504,
                }
            ],
        }
    )
    detail["gridAccounting"] = {
        **detail["gridAccounting"],
        "availableIndependentPairCount": 243,
        "excludedIndependentPairCount": 1,
        "commonComparableFactorCount": 60,
        "exclusionReasonCounts": {"insufficient_observations": 1},
    }
    summary["gridAccounting"] = deepcopy(detail["gridAccounting"])


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"expectedIndependentPairCount": 999}
            ),
            "expectedIndependentPairCount is inconsistent",
        ),
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"availableIndependentPairCount": 0}
            ),
            "availableIndependentPairCount is inconsistent",
        ),
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"evaluatedIndependentPairCount": 0}
            ),
            "evaluatedIndependentPairCount is inconsistent",
        ),
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"excludedIndependentPairCount": 1}
            ),
            "excludedIndependentPairCount is inconsistent",
        ),
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"missingIndependentPairCount": 1}
            ),
            "missingIndependentPairCount is inconsistent",
        ),
        (
            lambda artifact: artifact.detail["gridAccounting"].update(
                {"expectedIndependentPairCount": True}
            ),
            "expectedIndependentPairCount is inconsistent",
        ),
    ],
)
def test_rejects_inconsistent_independent_grid_counts(
    mutator,
    message: str,
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    mutator(artifact)

    with pytest.raises(StaticGridContractError, match=message):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_inconsistent_independent_exclusion_reason_totals(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    _add_excluded_independent_pair(artifact)
    artifact.detail["gridAccounting"]["exclusionReasonCounts"] = {"fabricated_reason": 1}
    artifact.summary["gridAccounting"] = deepcopy(artifact.detail["gridAccounting"])

    with pytest.raises(StaticGridContractError, match="exclusionReasonCounts is inconsistent"):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_summary_grid_accounting_that_differs_from_detail(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    artifact.summary["gridAccounting"] = {
        **artifact.summary["gridAccounting"],
        "expectedIndependentPairCount": 999,
    }

    with pytest.raises(StaticGridContractError, match="summary.gridAccounting differs"):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_exclusion_code_that_differs_from_structured_reason(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    _add_excluded_independent_pair(artifact)
    excluded = next(
        row
        for row in artifact.detail["factorPolicyRanking"]
        if row["comparison_status"] == "insufficient_history"
    )
    excluded["exclusion_reason_codes"] = ["fabricated_reason"]

    with pytest.raises(StaticGridContractError, match="reason codes differ"):
        write_static_grid(
            tmp_path / "data",
            [artifact],
            default_result_key=_result_key(artifact),
        )


def test_rejects_duplicate_result_keys_and_input_tuples(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    with pytest.raises(StaticGridContractError, match="duplicate resultKey"):
        write_static_grid(
            tmp_path / "duplicate-key",
            [artifact, artifact],
            default_result_key=_result_key(artifact),
        )

    first = _artifact(canonical_actual_artifact, market_variant="first")
    second = _artifact(canonical_actual_artifact, market_variant="second")

    with pytest.raises(StaticGridContractError, match="duplicate normalized input tuple"):
        write_static_grid(
            tmp_path / "duplicate-inputs",
            [first, second],
            default_result_key=_result_key(first),
        )


def test_rejects_missing_default_and_bound_overflow(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    with pytest.raises(StaticGridContractError, match="not present"):
        write_static_grid(
            tmp_path / "missing-default",
            [artifact],
            default_result_key="f" * 64,
        )
    with pytest.raises(StaticGridContractError, match="cannot exceed"):
        write_static_grid(
            tmp_path / "bad-bound",
            [artifact],
            default_result_key=_result_key(artifact),
            max_entries=MAX_STATIC_GRID_ENTRIES + 1,
        )


def test_validator_fails_closed_on_missing_hash_and_manifest_parity(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    artifact = _artifact(canonical_actual_artifact)
    result_key = _result_key(artifact)
    manifest_path = write_static_grid(
        tmp_path / "data",
        [artifact],
        default_result_key=result_key,
    )["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["entries"][0]
    detail_path = manifest_path.parent / entry["detail"]["path"]
    original = detail_path.read_bytes()
    replacement = b"[" + original[1:]
    detail_path.write_bytes(replacement)
    with pytest.raises(StaticGridContractError, match="SHA-256 differs"):
        validate_static_grid(manifest_path)

    detail_path.write_bytes(original + b"\n")
    with pytest.raises(StaticGridContractError, match="byte count differs"):
        validate_static_grid(manifest_path)
    detail_path.unlink()
    with pytest.raises(StaticGridContractError, match="missing or unreadable"):
        validate_static_grid(manifest_path)

    manifest["entries"][0]["normalizedInputs"]["top_n"] = 999
    with pytest.raises(StaticGridContractError, match="differs from identity"):
        validate_manifest(manifest)


def test_validator_rejects_alias_that_is_not_default_copy(
    canonical_actual_artifact: StaticGridArtifact,
    tmp_path: Path,
) -> None:
    first = _artifact(canonical_actual_artifact, top_n=20)
    second = _artifact(canonical_actual_artifact, top_n=30)
    manifest_path = write_static_grid(
        tmp_path / "data",
        [first, second],
        default_result_key=_result_key(first),
        write_default_aliases=True,
    )["manifest"]
    other_bytes = (manifest_path.parent / f"results/{_result_key(second)}.json").read_bytes()
    alias_path = manifest_path.parent / "latest.json"
    alias_path.write_bytes(other_bytes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reference = manifest["defaultAliases"]["artifacts"]["latestDetail"]
    reference["bytes"] = len(other_bytes)
    reference["sha256"] = hashlib.sha256(other_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StaticGridContractError, match="not a byte-for-byte copy"):
        validate_static_grid(manifest_path)


def test_current_three_entry_actual_grid_round_trips_through_publication_boundary(
    tmp_path: Path,
) -> None:
    manifest_path = ROOT / "docs" / "data" / "grid" / "v1" / "manifest.json"
    manifest = validate_static_grid(manifest_path)
    assert manifest["entryCount"] == 3

    artifacts = [
        StaticGridArtifact(
            detail=json.loads(
                (manifest_path.parent / entry["detail"]["path"]).read_text(encoding="utf-8")
            ),
            summary=json.loads(
                (manifest_path.parent / entry["summary"]["path"]).read_text(encoding="utf-8")
            ),
            preset_id=entry.get("presetId"),
        )
        for entry in manifest["entries"]
    ]
    rebuilt_path = write_static_grid(
        tmp_path / "data",
        artifacts,
        default_result_key=manifest["defaultResultKey"],
        write_default_aliases=True,
    )["manifest"]
    rebuilt = validate_static_grid(rebuilt_path)

    assert rebuilt["entryCount"] == 3
    assert rebuilt["defaultResultKey"] == manifest["defaultResultKey"]
    assert {entry["resultKey"] for entry in rebuilt["entries"]} == {
        entry["resultKey"] for entry in manifest["entries"]
    }
