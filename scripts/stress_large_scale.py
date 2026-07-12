from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from momentum_factor_lab.config import WEIGHTING_POLICIES, RunConfig
from momentum_factor_lab.dashboard import write_dashboard_site
from momentum_factor_lab.identity import (
    RESULT_IDENTITY_VERSION,
    canonical_sha256,
    normalized_research_inputs,
)
from momentum_factor_lab.workflow import (
    _absolute_guardrail_profile,
    _analysis_prices,
    _latest_portfolios,
    _policy_context,
    _validated_current_unavailable_reasons,
    result_payload,
    run_analysis,
    write_result_json,
)


MINIMUM_SCALE_SYMBOLS = 2_701
EXPECTED_FACTOR_COUNT = 64
EXPECTED_INDEPENDENT_FACTOR_COUNT = 61
EXPECTED_ALIAS_FACTOR_COUNT = 3
EXPECTED_INDEPENDENT_PAIR_COUNT = len(WEIGHTING_POLICIES) * EXPECTED_INDEPENDENT_FACTOR_COUNT
EXPECTED_ALIAS_PAIR_COUNT = len(WEIGHTING_POLICIES) * EXPECTED_ALIAS_FACTOR_COUNT
EXPECTED_POLICY_FACTOR_RUN_COUNT = len(WEIGHTING_POLICIES) * EXPECTED_FACTOR_COUNT
LONGEST_RAW_SIGNAL_FORMATION_SESSIONS = 294  # 252-day lookback plus the 42-day skip.


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic synthetic 2701+-symbol scale/contract stress case. "
            "This is not actual-market evidence and must not be published as a live result."
        )
    )
    parser.add_argument("--symbols", type=int, default=MINIMUM_SCALE_SYMBOLS)
    parser.add_argument("--start-date", default="2019-01-01")
    parser.add_argument("--end-date", default="2023-02-28")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--missing-ratio", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def _max_rss_bytes(usage: resource.struct_rusage) -> int:
    # macOS reports bytes; Linux reports KiB.
    return int(usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024)


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, (bool, np.bool_))
        and isinstance(value, (int, float, np.integer, np.floating))
        and np.isfinite(float(value))
    )


def _close(left: object, right: object, *, atol: float = 1e-9) -> bool:
    return (
        _finite_number(left)
        and _finite_number(right)
        and bool(np.isclose(float(left), float(right), rtol=0.0, atol=atol))
    )


def _record_number(value: object) -> float | int | None:
    if not _finite_number(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _append_if(condition: bool, failures: list[str], message: str) -> None:
    if condition:
        failures.append(message)


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _reject_public_output_paths(args: argparse.Namespace) -> None:
    public_docs = Path(__file__).resolve().parents[1] / "docs"
    protected = {
        "output-dir": args.output_dir,
        "site-dir": args.site_dir,
        "report": args.report,
    }
    violations = [name for name, path in protected.items() if _under(path, public_docs)]
    if violations:
        raise ValueError(
            "synthetic stress artifacts may not be written under public docs/: "
            + ", ".join(violations)
        )


def _concentration_expectations(weights: list[float], cash: float) -> dict[str, float]:
    invested = float(sum(weights))
    normalized = [weight / invested for weight in weights] if invested > 0.0 else []
    hhi = float(sum(weight * weight for weight in normalized))
    ordered = sorted(weights, reverse=True)
    return {
        "investedWeight": invested,
        "cashWeight": cash,
        "riskySleeveHhi": hhi,
        "effectiveNames": 1.0 / hhi if hhi > 0.0 else 0.0,
        "top1Weight": float(sum(ordered[:1])),
        "top5Weight": float(sum(ordered[:5])),
        "maxWeight": float(ordered[0] if ordered else 0.0),
    }


def _portfolio_invariant_failures(
    portfolio: object,
    *,
    label: str,
    factor: str,
    policy_id: str,
    as_of: str,
    config: RunConfig,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(portfolio, dict):
        return [f"{label}:not_an_object"]

    _append_if(portfolio.get("factor") != factor, failures, f"{label}:factor_identity")
    _append_if(
        portfolio.get("weightingPolicyId") != policy_id,
        failures,
        f"{label}:policy_identity",
    )
    _append_if(
        portfolio.get("weightingPolicyVersion") != "1",
        failures,
        f"{label}:policy_version",
    )
    _append_if(
        portfolio.get("asOf") != as_of or portfolio.get("signalDate") != as_of,
        failures,
        f"{label}:as_of_signal_date",
    )
    _append_if(
        portfolio.get("targetType") != "current_research_target",
        failures,
        f"{label}:target_type",
    )
    _append_if(
        not str(portfolio.get("executionTiming") or "").strip(),
        failures,
        f"{label}:execution_timing",
    )
    _append_if(
        not str(portfolio.get("tieBreakPolicy") or "").strip(),
        failures,
        f"{label}:tie_break_policy",
    )
    _append_if(
        not isinstance(portfolio.get("componentStatus"), dict),
        failures,
        f"{label}:component_status",
    )
    reasons = portfolio.get("reasons")
    _append_if(
        not isinstance(reasons, list) or any(not str(reason).strip() for reason in reasons or []),
        failures,
        f"{label}:reasons",
    )

    rows = portfolio.get("weights")
    cash = portfolio.get("cashWeight")
    status = portfolio.get("status")
    if not isinstance(rows, list):
        return [*failures, f"{label}:weights_not_a_list"]
    if not _finite_number(cash) or not 0.0 <= float(cash) <= 1.0:
        return [*failures, f"{label}:invalid_cash_weight"]
    if status not in {"available", "unavailable"}:
        failures.append(f"{label}:invalid_status")
    if status == "available" and not rows:
        failures.append(f"{label}:available_without_holdings")
    if status == "unavailable" and (rows or not _close(cash, 1.0)):
        failures.append(f"{label}:unavailable_not_cash_only")

    eligible_count = portfolio.get("eligibleSecurityCount")
    selected_count = portfolio.get("selectedSecurityCount")
    if not _finite_number(eligible_count) or float(eligible_count) < len(rows):
        failures.append(f"{label}:eligible_count")
    if not _finite_number(selected_count) or int(float(selected_count)) != len(rows):
        failures.append(f"{label}:selected_count")
    if len(rows) > config.top_n:
        failures.append(f"{label}:top_n")

    symbols: list[str] = []
    weights: list[float] = []
    ranks: list[int] = []
    for row_index, row in enumerate(rows, start=1):
        row_label = f"{label}:holding_{row_index}"
        if not isinstance(row, dict):
            failures.append(f"{row_label}:not_an_object")
            continue
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            failures.append(f"{row_label}:symbol")
        else:
            symbols.append(symbol)
        rank = row.get("rank")
        if not _finite_number(rank) or not float(rank).is_integer() or int(rank) < 1:
            failures.append(f"{row_label}:rank")
        else:
            ranks.append(int(rank))
        weight = row.get("weight")
        if not _finite_number(weight) or not 0.0 < float(weight) <= config.max_weight + 1e-12:
            failures.append(f"{row_label}:weight")
        else:
            weights.append(float(weight))
        if not _finite_number(row.get("factorScore")):
            failures.append(f"{row_label}:factor_score")
        if not _finite_number(row.get("latestPrice")) or float(row["latestPrice"]) <= 0.0:
            failures.append(f"{row_label}:latest_price")
        if row.get("eligibilityStatus") != "eligible":
            failures.append(f"{row_label}:eligibility")
        if not _close(row.get("maxWeight"), config.max_weight):
            failures.append(f"{row_label}:declared_max_weight")

    if len(symbols) != len(set(symbols)):
        failures.append(f"{label}:duplicate_symbols")
    if ranks != list(range(1, len(rows) + 1)):
        failures.append(f"{label}:rank_sequence")
    if len(weights) == len(rows) and not _close(sum(weights) + float(cash), 1.0):
        failures.append(f"{label}:weights_plus_cash")

    concentration = portfolio.get("concentration")
    if not isinstance(concentration, dict):
        failures.append(f"{label}:concentration_missing")
    elif len(weights) == len(rows):
        expected = _concentration_expectations(weights, float(cash))
        for field, value in expected.items():
            if not _close(concentration.get(field), value):
                failures.append(f"{label}:concentration_{field}")

    selection_fraction = portfolio.get("selectionFraction")
    if _finite_number(eligible_count) and float(eligible_count) > 0.0:
        expected_fraction = len(rows) / float(eligible_count)
    else:
        expected_fraction = 0.0
    if not _close(selection_fraction, expected_fraction):
        failures.append(f"{label}:selection_fraction")
    return failures


def _portfolio_signature(portfolio: dict[str, Any]) -> tuple[object, ...]:
    rows = portfolio.get("weights", [])
    return (
        portfolio.get("status"),
        float(portfolio.get("cashWeight", np.nan)),
        tuple(
            (str(row.get("symbol")), float(row.get("weight", np.nan)))
            for row in rows
            if isinstance(row, dict)
        ),
    )


def _same_portfolio_signature(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_status, left_cash, left_rows = _portfolio_signature(left)
    right_status, right_cash, right_rows = _portfolio_signature(right)
    if left_status != right_status or not _close(left_cash, right_cash):
        return False
    if len(left_rows) != len(right_rows):
        return False
    return all(
        left_symbol == right_symbol and _close(left_weight, right_weight)
        for (left_symbol, left_weight), (right_symbol, right_weight) in zip(
            left_rows, right_rows, strict=True
        )
    )


def _validate_payload_contract(
    payload: dict[str, Any],
    *,
    args: argparse.Namespace,
    config: RunConfig,
) -> list[str]:
    failures: list[str] = []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    scope = payload.get("researchScope") if isinstance(payload.get("researchScope"), dict) else {}
    expected_counts = {
        "requestedCandidateCount": args.symbols,
        "providerReturnedCandidateCount": args.symbols,
        "inputSecurityCount": args.symbols,
        "analyzedSecurityCount": args.symbols,
    }
    _append_if(payload.get("schemaVersion") != 4, failures, "payload:schema_version")
    _append_if(data.get("mode") != "demo", failures, "payload:data_mode_not_demo")
    _append_if(data.get("synthetic") is not True, failures, "payload:not_marked_synthetic")
    _append_if(
        scope.get("evidenceStatus") != "same_sample_descriptive",
        failures,
        "payload:synthetic_evidence_status",
    )
    _append_if(scope.get("researchOnly") is not True, failures, "payload:research_only")
    _append_if(
        scope.get("notInvestmentRecommendation") is not True,
        failures,
        "payload:not_investment_recommendation",
    )
    for field, expected in expected_counts.items():
        _append_if(data.get(field) != expected, failures, f"payload:{field}")
    _append_if(
        not _finite_number(data.get("inputSecurityCount"))
        or int(data["inputSecurityCount"]) < MINIMUM_SCALE_SYMBOLS,
        failures,
        "payload:input_below_2701",
    )
    _append_if(meta.get("factorCount") != EXPECTED_FACTOR_COUNT, failures, "payload:factor_count")
    _append_if(
        meta.get("independentFactorCount") != EXPECTED_INDEPENDENT_FACTOR_COUNT,
        failures,
        "payload:independent_factor_count",
    )
    _append_if(
        meta.get("aliasFactorCount") != EXPECTED_ALIAS_FACTOR_COUNT,
        failures,
        "payload:alias_factor_count",
    )
    _append_if(meta.get("policyCount") != len(WEIGHTING_POLICIES), failures, "payload:policy_count")
    _append_if(
        meta.get("policyFactorRunCount") != EXPECTED_POLICY_FACTOR_RUN_COUNT,
        failures,
        "payload:policy_factor_run_count",
    )

    result_key = payload.get("resultKey")
    identity = payload.get("resultIdentity")
    if not isinstance(identity, dict):
        failures.append("payload:result_identity")
        identity = {}
    key_parts = identity.get("keyParts")
    _append_if(
        not isinstance(result_key, str)
        or len(result_key) != 64
        or any(character not in "0123456789abcdef" for character in str(result_key)),
        failures,
        "payload:result_key",
    )
    _append_if(identity.get("resultKey") != result_key, failures, "payload:identity_key_parity")
    _append_if(
        identity.get("identityVersion") != RESULT_IDENTITY_VERSION,
        failures,
        "payload:identity_version",
    )
    if not isinstance(key_parts, dict):
        failures.append("payload:identity_key_parts")
        key_parts = {}
    else:
        _append_if(
            canonical_sha256(key_parts) != result_key,
            failures,
            "payload:identity_key_recomputation",
        )
    _append_if(
        key_parts.get("normalizedInputs") != normalized_research_inputs(config),
        failures,
        "payload:identity_normalized_inputs",
    )
    identity_market = (
        key_parts.get("marketSnapshot") if isinstance(key_parts.get("marketSnapshot"), dict) else {}
    )
    for field, expected in {
        "sourceMode": "demo",
        "dataAsOf": data.get("asOf"),
        "requestedCandidateCount": args.symbols,
        "providerReturnedCandidateCount": args.symbols,
        "analyzedSecurityCount": args.symbols,
    }.items():
        _append_if(
            identity_market.get(field) != expected,
            failures,
            f"payload:identity_market:{field}",
        )

    ranking = payload.get("factorPolicyRanking")
    diagnostics = payload.get("policyDiagnostics")
    accounting = payload.get("gridAccounting")
    registry = payload.get("weightingPolicyRegistry")
    if not isinstance(ranking, list) or len(ranking) != EXPECTED_POLICY_FACTOR_RUN_COUNT:
        failures.append("payload:joint_grid_length")
        ranking = []
    if not isinstance(diagnostics, list) or len(diagnostics) != len(WEIGHTING_POLICIES):
        failures.append("payload:policy_diagnostics_length")
        diagnostics = []
    if not isinstance(accounting, dict):
        failures.append("payload:grid_accounting")
        accounting = {}
    if not isinstance(registry, dict) or not isinstance(registry.get("policies"), dict):
        failures.append("payload:policy_registry")
        policies: dict[str, Any] = {}
    else:
        policies = registry["policies"]
    _append_if(set(policies) != set(WEIGHTING_POLICIES), failures, "payload:policy_registry_ids")
    _append_if("score_liquidity_rank" not in policies, failures, "payload:liquidity_policy_missing")
    for policy_id, definition in policies.items():
        label = f"policy_registry:{policy_id}"
        if not isinstance(definition, dict):
            failures.append(f"{label}:definition")
            continue
        for field in ("version", "implementationId", "formula", "requiredSignalDateInputs"):
            _append_if(not definition.get(field), failures, f"{label}:{field}")
        _append_if(
            "market_cap" in str(definition.get("formula", "")).lower(),
            failures,
            f"{label}:market_cap_special_case",
        )

    rows = [row for row in ranking if isinstance(row, dict)]
    _append_if(len(rows) != len(ranking), failures, "payload:joint_grid_non_object_row")
    factors = {str(row.get("factor")) for row in rows if row.get("factor") is not None}
    _append_if(len(factors) != EXPECTED_FACTOR_COUNT, failures, "payload:factor_id_set")
    observed_pairs = [(str(row.get("policy_id")), str(row.get("factor"))) for row in rows]
    _append_if(
        len(observed_pairs) != len(set(observed_pairs)),
        failures,
        "payload:duplicate_factor_policy_pair",
    )
    expected_grid = {(policy_id, factor) for policy_id in WEIGHTING_POLICIES for factor in factors}
    _append_if(set(observed_pairs) != expected_grid, failures, "payload:joint_cross_product")

    alias_rows = [row for row in rows if row.get("comparison_status") == "duplicate_alias"]
    alias_factors = {str(row.get("factor")) for row in alias_rows}
    independent_factors = factors.difference(alias_factors)
    independent_rows = [row for row in rows if str(row.get("factor")) in independent_factors]
    _append_if(len(alias_factors) != EXPECTED_ALIAS_FACTOR_COUNT, failures, "payload:alias_factors")
    _append_if(len(alias_rows) != EXPECTED_ALIAS_PAIR_COUNT, failures, "payload:alias_rows")
    _append_if(
        len(independent_factors) != EXPECTED_INDEPENDENT_FACTOR_COUNT,
        failures,
        "payload:independent_factors",
    )
    _append_if(
        len(independent_rows) != EXPECTED_INDEPENDENT_PAIR_COUNT,
        failures,
        "payload:independent_pair_count",
    )
    for row in alias_rows:
        label = f"joint_grid:{row.get('policy_id')}:{row.get('factor')}"
        _append_if(row.get("comparison_eligible") is not False, failures, f"{label}:alias_eligible")
        _append_if(row.get("selected") is not False, failures, f"{label}:alias_selected")
        codes = row.get("exclusion_reason_codes")
        _append_if(
            not isinstance(codes, list) or "duplicate_alias" not in codes,
            failures,
            f"{label}:alias_reason",
        )

    finite_grid_fields = (
        "cagr",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "annualized_turnover",
        "annualized_cost_drag",
        "valuation_coverage_ratio",
        "policy_input_coverage_ratio",
        "execution_coverage_ratio",
        "median_target_effective_names",
        "median_target_hhi",
        "median_target_cash_weight",
        "median_target_top1_weight",
        "median_target_top5_weight",
        "min_target_effective_names",
        "max_target_hhi",
        "max_target_weight",
        "current_target_effective_names",
        "current_target_hhi",
        "current_target_max_weight",
        "base_composite_score",
        "max_abs_security_day_contribution",
        "max_abs_security_observation_contribution",
        "max_security_absolute_contribution_share",
        "absolute_contribution_hhi",
        "max_abs_leave_one_security_cagr_delta",
        "attribution_max_residual",
    )
    standard_guardrail_fields = (
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
    contribution_guardrail_fields = (
        "guardrail_security_day_contribution",
        "guardrail_security_absolute_contribution_share",
        "guardrail_leave_one_security",
    )
    guardrail_fields = (
        *standard_guardrail_fields,
        *contribution_guardrail_fields,
        "standard_guardrail_pass",
        "contribution_guardrail_pass",
        "absolute_guardrail_pass",
        "selection_eligible",
        "selected",
    )
    available_independent_rows = [
        row for row in independent_rows if row.get("comparison_status") == "available"
    ]
    for row in rows:
        policy_id = str(row.get("policy_id"))
        factor = str(row.get("factor"))
        label = f"joint_grid:{policy_id}:{factor}"
        reasons = row.get("exclusion_reasons")
        codes = row.get("exclusion_reason_codes")
        if row.get("comparison_status") == "available":
            _append_if(reasons != [] or codes != [], failures, f"{label}:unexpected_exclusion")
            for field in finite_grid_fields:
                if not _finite_number(row.get(field)):
                    failures.append(f"{label}:{field}")
        else:
            _append_if(
                not isinstance(reasons, list) or not reasons,
                failures,
                f"{label}:missing_exclusion_detail",
            )
            _append_if(
                not isinstance(codes, list) or not codes,
                failures,
                f"{label}:missing_exclusion_code",
            )
        for field in guardrail_fields:
            _append_if(
                not isinstance(row.get(field), (bool, np.bool_)),
                failures,
                f"{label}:{field}_not_boolean",
            )
        standard = all(bool(row.get(field)) for field in standard_guardrail_fields)
        contribution = all(bool(row.get(field)) for field in contribution_guardrail_fields)
        _append_if(
            row.get("standard_guardrail_pass") is not standard,
            failures,
            f"{label}:standard_guardrail_reconciliation",
        )
        _append_if(
            row.get("contribution_guardrail_pass") is not contribution,
            failures,
            f"{label}:contribution_guardrail_reconciliation",
        )
        _append_if(
            row.get("absolute_guardrail_pass") is not (standard and contribution),
            failures,
            f"{label}:absolute_guardrail_reconciliation",
        )
        if row.get("comparison_status") != "available":
            continue
        for field, minimum in (
            ("observations", config.min_evaluation_observations),
            ("daily_risk_observations", config.min_daily_risk_observations),
        ):
            if not _finite_number(row.get(field)) or float(row[field]) < minimum:
                failures.append(f"{label}:{field}_guardrail")
        if not _close(row.get("policy_input_coverage_ratio"), 1.0):
            failures.append(f"{label}:policy_input_coverage")
        if not _close(row.get("execution_coverage_ratio"), 1.0):
            failures.append(f"{label}:execution_coverage")
        if not _close(row.get("valuation_coverage_ratio"), 1.0):
            failures.append(f"{label}:valuation_coverage")
        if not _close(row.get("blocked_execution_count"), 0.0):
            failures.append(f"{label}:blocked_execution")
        if not _close(row.get("total_unpriceable_target_count"), 0.0):
            failures.append(f"{label}:unpriceable_targets")
        if (
            _finite_number(row.get("max_target_weight"))
            and float(row["max_target_weight"]) > config.max_weight + 1e-12
        ):
            failures.append(f"{label}:historical_max_weight")

    selected_policy = payload.get("selectedWeightingPolicy")
    selected_factor = payload.get("selectedFactor")
    _append_if(selected_policy not in WEIGHTING_POLICIES, failures, "payload:selected_policy")
    _append_if(selected_factor not in factors, failures, "payload:selected_factor")
    selected_rows = [row for row in rows if row.get("selected") is True]
    if (
        len(selected_rows) != 1
        or selected_rows[0].get("rank") != 1
        or selected_rows[0].get("comparison_status") != "available"
        or selected_rows[0].get("selection_eligible") is not True
        or selected_rows[0].get("absolute_guardrail_pass") is not True
        or selected_rows[0].get("factor") != selected_factor
        or selected_rows[0].get("policy_id") != selected_policy
    ):
        failures.append("payload:selected_joint_row")
    ranked_rows = [row for row in rows if _finite_number(row.get("rank"))]
    observed_ranks = sorted(int(float(row["rank"])) for row in ranked_rows)
    _append_if(
        observed_ranks != list(range(1, len(ranked_rows) + 1)),
        failures,
        "payload:joint_rank_sequence",
    )
    _append_if(
        any(row.get("selection_eligible") is not True for row in ranked_rows),
        failures,
        "payload:ranked_row_not_eligible",
    )

    accounting_expected = {
        "independentFactorCount": EXPECTED_INDEPENDENT_FACTOR_COUNT,
        "policyCount": len(WEIGHTING_POLICIES),
        "expectedIndependentPairCount": EXPECTED_INDEPENDENT_PAIR_COUNT,
        "evaluatedIndependentPairCount": EXPECTED_INDEPENDENT_PAIR_COUNT,
        "availableIndependentPairCount": len(available_independent_rows),
        "excludedIndependentPairCount": (
            EXPECTED_INDEPENDENT_PAIR_COUNT - len(available_independent_rows)
        ),
        "missingIndependentPairCount": 0,
        "diagnosticAliasFactorCount": EXPECTED_ALIAS_FACTOR_COUNT,
        "diagnosticAliasPairCount": EXPECTED_ALIAS_PAIR_COUNT,
    }
    for field, expected in accounting_expected.items():
        _append_if(accounting.get(field) != expected, failures, f"grid_accounting:{field}")
    common_count = sum(
        all(
            any(
                row.get("factor") == factor
                and row.get("policy_id") == policy_id
                and row.get("comparison_status") == "available"
                for row in independent_rows
            )
            for policy_id in WEIGHTING_POLICIES
        )
        for factor in independent_factors
    )
    _append_if(
        accounting.get("commonComparableFactorCount") != common_count,
        failures,
        "grid_accounting:commonComparableFactorCount",
    )
    observed_reason_counts: Counter[str] = Counter()
    for row in independent_rows:
        if row.get("comparison_status") != "available":
            observed_reason_counts.update(
                str(code) for code in row.get("exclusion_reason_codes", [])
            )
    _append_if(
        accounting.get("exclusionReasonCounts") != dict(sorted(observed_reason_counts.items())),
        failures,
        "grid_accounting:exclusionReasonCounts",
    )

    diagnostic_ids = [row.get("policy_id") for row in diagnostics if isinstance(row, dict)]
    _append_if(
        set(diagnostic_ids) != set(WEIGHTING_POLICIES)
        or len(diagnostic_ids) != len(set(diagnostic_ids)),
        failures,
        "payload:policy_diagnostic_ids",
    )
    diagnostic_finite_fields = (
        "cagr",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "annualized_turnover",
        "annualized_cost_drag",
        "median_target_effective_names",
        "median_target_hhi",
        "median_target_cash_weight",
        "median_target_top1_weight",
        "median_target_top5_weight",
        "max_target_weight",
        "max_abs_security_observation_contribution",
        "max_security_absolute_contribution_share",
        "max_abs_leave_one_security_cagr_delta",
    )
    for row in diagnostics:
        if not isinstance(row, dict):
            continue
        policy_id = str(row.get("policy_id"))
        label = f"policy_diagnostic:{policy_id}"
        _append_if(row.get("diagnostic_only") is not True, failures, f"{label}:not_diagnostic")
        for old_field in (
            "selected",
            "rank",
            "performance_rank",
            "default_eligible",
        ):
            _append_if(old_field in row, failures, f"{label}:legacy_field:{old_field}")
        if common_count:
            for field in diagnostic_finite_fields:
                if not _finite_number(row.get(field)):
                    failures.append(f"{label}:{field}")
        available_for_policy = sum(
            row_grid.get("policy_id") == policy_id
            and row_grid.get("comparison_status") == "available"
            for row_grid in independent_rows
        )
        if row.get("paired_factor_count") != common_count:
            failures.append(f"{label}:paired_factor_count")
        if row.get("available_factor_count") != available_for_policy:
            failures.append(f"{label}:available_factor_count")
        if row.get("excluded_factor_count") != (
            EXPECTED_INDEPENDENT_FACTOR_COUNT - available_for_policy
        ):
            failures.append(f"{label}:excluded_factor_count")
        expected_status = (
            "complete" if available_for_policy == EXPECTED_INDEPENDENT_FACTOR_COUNT else "partial"
        )
        if row.get("data_status") != expected_status:
            failures.append(f"{label}:data_status")
        if row.get("contains_selected_pair") is not (policy_id == selected_policy):
            failures.append(f"{label}:selected_pair_marker")

    decision = payload.get("selectionDecision")
    if not isinstance(decision, dict):
        failures.append("payload:selection_decision")
        decision = {}
    _append_if(decision.get("method") != "joint_factor_policy", failures, "decision:method")
    _append_if(decision.get("selectedFactor") != selected_factor, failures, "decision:factor")
    _append_if(decision.get("selectedPolicyId") != selected_policy, failures, "decision:policy")
    profile = decision.get("guardrailProfile")
    if not isinstance(profile, dict):
        failures.append("decision:absolute_guardrail_profile")
        profile = {}
    _append_if(profile.get("policyNeutral") is not True, failures, "decision:policy_neutral")
    _append_if("equalWeightBaseline" in profile, failures, "decision:equal_relative_guardrail")
    _append_if(
        profile.get("extremeEventAction") != config.selection_extreme_event_action,
        failures,
        "decision:extreme_event_action",
    )
    _append_if(
        profile != _absolute_guardrail_profile(config),
        failures,
        "decision:absolute_guardrail_profile_exact",
    )
    method = payload.get("selectionMethod")
    if not isinstance(method, dict):
        failures.append("payload:selection_method")
        method = {}
    _append_if(
        method.get("name") != "joint_factor_policy_absolute_guardrails",
        failures,
        "selection_method:name",
    )
    _append_if(
        method.get("policyAggregatesAreDiagnosticOnly") is not True,
        failures,
        "selection_method:diagnostic_only",
    )
    _append_if(
        method.get("equalWeightIsPeerCandidate") is not True,
        failures,
        "selection_method:equal_peer",
    )
    _append_if(
        method.get("guardrailVersion") != config.absolute_guardrail_version,
        failures,
        "selection_method:absolute_guardrail_version",
    )
    portfolio_policy = payload.get("portfolioPolicy")
    if not isinstance(portfolio_policy, dict):
        failures.append("payload:portfolio_policy")
        portfolio_policy = {}
    _append_if(
        portfolio_policy.get("selectedPolicyId") != selected_policy,
        failures,
        "portfolio_policy:selected_pair_parity",
    )
    aggregate_diagnostics = portfolio_policy.get("policyAggregateDiagnostics")
    _append_if(
        not isinstance(aggregate_diagnostics, dict)
        or aggregate_diagnostics.get("diagnosticOnly") is not True
        or aggregate_diagnostics.get("selectedByPolicyAggregate") is not False,
        failures,
        "portfolio_policy:aggregate_not_diagnostic_only",
    )

    selected_row = selected_rows[0] if len(selected_rows) == 1 else {}
    contribution = payload.get("contributionDiagnostics")
    if not isinstance(contribution, dict):
        failures.append("payload:contribution_diagnostics")
        contribution = {}
    _append_if(contribution.get("complete") is not True, failures, "contribution:incomplete")
    _append_if(
        contribution.get("observedReturnsPreserved") is not True,
        failures,
        "contribution:observed_returns",
    )
    _append_if(contribution.get("reoptimized") is not False, failures, "contribution:reoptimized")
    for payload_field, row_field in {
        "maxAbsSecurityDayContribution": "max_abs_security_day_contribution",
        "maxSecurityAbsoluteContributionShare": "max_security_absolute_contribution_share",
        "maxLeaveOneSecurityCagrDelta": "max_abs_leave_one_security_cagr_delta",
        "attributionMaxResidual": "attribution_max_residual",
    }.items():
        _append_if(
            not _close(contribution.get(payload_field), selected_row.get(row_field)),
            failures,
            f"contribution:selected_row_parity:{payload_field}",
        )
    for event_field in (
        "maxExactSingleSessionSecurityContribution",
        "maxObservedIntervalSecurityContribution",
    ):
        event = contribution.get(event_field)
        if event is not None:
            _append_if(
                not isinstance(event, dict)
                or not str(event.get("symbol") or "").strip()
                or not str(event.get("date") or "").strip(),
                failures,
                f"contribution:{event_field}",
            )

    performance = payload.get("performance")
    if not isinstance(performance, dict) or performance.get("weightingPolicyId") != selected_policy:
        failures.append("payload:performance_policy")

    target = payload.get("currentResearchTarget")
    if not isinstance(target, dict):
        failures.append("payload:current_research_target")
        target = {}
    else:
        failures.extend(
            _portfolio_invariant_failures(
                target,
                label=f"payload_current:{selected_policy}:{selected_factor}",
                factor=str(selected_factor),
                policy_id=str(selected_policy),
                as_of=str(data.get("asOf")),
                config=config,
            )
        )

    transition = payload.get("currentTransition")
    held = payload.get("backtestHeldPortfolio")
    if not isinstance(transition, dict) or not isinstance(held, dict) or not target:
        failures.append("payload:current_transition_objects")
    else:
        held_weights = {
            str(row.get("symbol")): float(row.get("weight"))
            for row in held.get("weights", [])
            if isinstance(row, dict) and _finite_number(row.get("weight"))
        }
        target_weights = {
            str(row.get("symbol")): float(row.get("weight"))
            for row in target.get("weights", [])
            if isinstance(row, dict) and _finite_number(row.get("weight"))
        }
        symbols = set(held_weights) | set(target_weights)
        expected_turnover = 0.5 * (
            sum(
                abs(target_weights.get(symbol, 0.0) - held_weights.get(symbol, 0.0))
                for symbol in symbols
            )
            + abs(float(target.get("cashWeight", np.nan)) - float(held.get("cashWeight", np.nan)))
        )
        if transition.get("valuationAvailable") is True:
            if not _close(transition.get("oneWayTurnover"), expected_turnover):
                failures.append("payload:current_transition_turnover")
            expected_cost = expected_turnover * config.total_cost_rate
            if not _close(transition.get("modeledCostFraction"), expected_cost):
                failures.append("payload:current_transition_cost")
        if transition.get("actualNextClosePretradeDriftKnown") is not False:
            failures.append("payload:current_transition_future_drift")
    return failures


def _recompute_all_current_portfolios(
    result: Any,
    payload: dict[str, Any],
) -> tuple[list[str], dict[str, dict[str, Any]], int]:
    """Independently rebuild every policy/factor current target and validate it."""

    config = result.config
    market = result.market_data
    as_of = market.as_of.date().isoformat()
    selected_policy = str(payload["selectedWeightingPolicy"])
    selected_factor = str(payload["selectedFactor"])
    serialized_target = payload["currentResearchTarget"]
    context_sessions = max(
        config.volatility_lookback_days + 1,
        config.liquidity_lookback_days,
    )
    prices = _analysis_prices(market).tail(context_sessions)
    dollar_volumes = market.dollar_volumes.reindex(
        index=prices.index,
        columns=prices.columns,
    )
    volatility, liquidity = _policy_context(prices, dollar_volumes, config)
    failures: list[str] = []
    summaries: dict[str, dict[str, Any]] = {}
    checked = 0
    serialized_rows: dict[tuple[str, str], dict[str, Any]] = {}
    ranking = payload.get("factorPolicyRanking")
    if not isinstance(ranking, list):
        failures.append("recomputed_current:serialized_ranking_not_a_list")
        ranking = []
    for row in ranking:
        if not isinstance(row, dict):
            failures.append("recomputed_current:serialized_ranking_non_object_row")
            continue
        pair = (str(row.get("policy_id")), str(row.get("factor")))
        if pair in serialized_rows:
            failures.append(f"recomputed_current:duplicate_serialized_pair:{pair[0]}:{pair[1]}")
            continue
        serialized_rows[pair] = row

    expected_pairs = {
        (policy_id, factor) for policy_id in WEIGHTING_POLICIES for factor in result.factor_scores
    }
    if set(serialized_rows) != expected_pairs:
        failures.append("recomputed_current:serialized_pair_set")
    for policy_id in WEIGHTING_POLICIES:
        portfolios = _latest_portfolios(
            result.factor_scores,
            market,
            config,
            policy_id,
            volatility,
            liquidity,
        )
        if set(portfolios) != set(result.factor_scores):
            failures.append(f"recomputed_current:{policy_id}:factor_set")
        available = 0
        holdings: list[float] = []
        effective_names: list[float] = []
        hhi_values: list[float] = []
        cash_values: list[float] = []
        top1_values: list[float] = []
        top5_values: list[float] = []
        max_weights: list[float] = []
        for factor, portfolio in portfolios.items():
            checked += 1
            portfolio_payload = portfolio.to_dict()
            label = f"recomputed_current:{policy_id}:{factor}"
            failures.extend(
                _portfolio_invariant_failures(
                    portfolio_payload,
                    label=label,
                    factor=factor,
                    policy_id=policy_id,
                    as_of=as_of,
                    config=config,
                )
            )
            if portfolio.status == "available":
                available += 1
            concentration = portfolio_payload.get("concentration", {})
            holdings.append(float(portfolio_payload["selectedSecurityCount"]))
            cash_values.append(float(portfolio_payload["cashWeight"]))
            if isinstance(concentration, dict):
                effective_names.append(float(concentration.get("effectiveNames", np.nan)))
                hhi_values.append(float(concentration.get("riskySleeveHhi", np.nan)))
                top1_values.append(float(concentration.get("top1Weight", np.nan)))
                top5_values.append(float(concentration.get("top5Weight", np.nan)))
                max_weights.append(float(concentration.get("maxWeight", np.nan)))
            serialized_row = serialized_rows.get((policy_id, factor))
            if serialized_row is None:
                failures.append(f"{label}:serialized_current_row_missing")
            elif not isinstance(concentration, dict):
                failures.append(f"{label}:recomputed_concentration_missing")
            else:
                available_now = portfolio.status == "available"
                exact_current_fields = {
                    "current_portfolio_available": available_now,
                    "current_holding_count": portfolio_payload["selectedSecurityCount"],
                    "current_portfolio_input_reasons": (
                        []
                        if available_now
                        else _validated_current_unavailable_reasons(
                            portfolio_payload["reasons"],
                            factor=factor,
                            policy_id=policy_id,
                            date=portfolio.as_of,
                        )
                    ),
                    "guardrail_current_target": available_now,
                    "guardrail_current_effective_names": (
                        float(concentration["effectiveNames"])
                        >= config.selection_min_effective_names
                    ),
                    "guardrail_current_target_hhi": (
                        float(concentration["riskySleeveHhi"]) <= config.selection_max_target_hhi
                    ),
                    "guardrail_current_target_weight": (
                        float(concentration["maxWeight"]) <= config.selection_max_target_weight
                    ),
                }
                for field, expected in exact_current_fields.items():
                    if serialized_row.get(field) != expected:
                        failures.append(f"{label}:serialized_current_row_{field}")
                numeric_current_fields = {
                    "current_cash_weight": portfolio_payload["cashWeight"],
                    "current_target_effective_names": concentration["effectiveNames"],
                    "current_target_hhi": concentration["riskySleeveHhi"],
                    "current_target_max_weight": concentration["maxWeight"],
                }
                for field, expected in numeric_current_fields.items():
                    if not _close(serialized_row.get(field), expected):
                        failures.append(f"{label}:serialized_current_row_{field}")
            if policy_id == selected_policy and factor == selected_factor:
                if not _same_portfolio_signature(portfolio_payload, serialized_target):
                    failures.append(f"{label}:serialized_current_target_parity")

        selected_factor_portfolio = portfolios[selected_factor].to_dict()
        selected_concentration = selected_factor_portfolio["concentration"]
        summaries[policy_id] = {
            "checkedPortfolioCount": len(portfolios),
            "availablePortfolioCount": available,
            "medianHoldingCount": float(np.median(holdings)),
            "medianCashWeight": float(np.median(cash_values)),
            "medianEffectiveNames": float(np.median(effective_names)),
            "medianRiskySleeveHhi": float(np.median(hhi_values)),
            "medianTop1Weight": float(np.median(top1_values)),
            "medianTop5Weight": float(np.median(top5_values)),
            "maximumObservedWeight": float(np.max(max_weights)),
            "selectedFactorCurrentTarget": {
                "factor": selected_factor,
                "status": selected_factor_portfolio["status"],
                "holdingCount": selected_factor_portfolio["selectedSecurityCount"],
                "cashWeight": selected_factor_portfolio["cashWeight"],
                "effectiveNames": selected_concentration["effectiveNames"],
                "riskySleeveHhi": selected_concentration["riskySleeveHhi"],
                "top1Weight": selected_concentration["top1Weight"],
                "top5Weight": selected_concentration["top5Weight"],
                "maxWeight": selected_concentration["maxWeight"],
            },
        }
        if available != EXPECTED_FACTOR_COUNT:
            failures.append(f"recomputed_current:{policy_id}:available_count:{available}")
    if checked != EXPECTED_POLICY_FACTOR_RUN_COUNT:
        failures.append(f"recomputed_current:checked_count:{checked}")
    return failures, summaries, checked


def _policy_report_rows(
    payload: dict[str, Any],
    current_summaries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_factor = payload["selectedFactor"]
    grid = payload["factorPolicyRanking"]
    diagnostic_by_policy = {row["policy_id"]: row for row in payload["policyDiagnostics"]}
    rows: list[dict[str, Any]] = []
    for policy_id in WEIGHTING_POLICIES:
        diagnostic = diagnostic_by_policy[policy_id]
        selected_factor_row = next(
            row
            for row in grid
            if row["policy_id"] == policy_id and row["factor"] == selected_factor
        )
        rows.append(
            {
                "policyId": policy_id,
                "diagnosticOnly": diagnostic["diagnostic_only"],
                "containsSelectedPair": diagnostic["contains_selected_pair"],
                "dataStatus": diagnostic["data_status"],
                "pairedIndependentFactorCount": diagnostic["paired_factor_count"],
                "availableIndependentFactorCount": diagnostic["available_factor_count"],
                "excludedIndependentFactorCount": diagnostic["excluded_factor_count"],
                "crossFactorMedianPerformance": {
                    metric: _record_number(diagnostic.get(metric))
                    for metric in (
                        "cagr",
                        "sharpe",
                        "sortino",
                        "calmar",
                        "max_drawdown",
                    )
                },
                "crossFactorMedianConcentration": {
                    "effectiveNames": _record_number(
                        diagnostic.get("median_target_effective_names")
                    ),
                    "riskySleeveHhi": _record_number(diagnostic.get("median_target_hhi")),
                    "cashWeight": _record_number(diagnostic.get("median_target_cash_weight")),
                    "top1Weight": _record_number(diagnostic.get("median_target_top1_weight")),
                    "top5Weight": _record_number(diagnostic.get("median_target_top5_weight")),
                    "maximumWeight": _record_number(diagnostic.get("max_target_weight")),
                },
                "crossFactorMedianTurnoverAndCost": {
                    "annualizedTurnover": _record_number(diagnostic.get("annualized_turnover")),
                    "annualizedCostDrag": _record_number(diagnostic.get("annualized_cost_drag")),
                },
                "selectedFactorPair": {
                    "factor": selected_factor,
                    "jointSelected": selected_factor_row["selected"],
                    "jointRank": _record_number(selected_factor_row.get("rank")),
                    "comparisonStatus": selected_factor_row["comparison_status"],
                    "selectionStatus": selected_factor_row["selection_status"],
                    "selectionEligible": selected_factor_row["selection_eligible"],
                    "selectionScore": _record_number(selected_factor_row.get("selection_score")),
                    "cagr": _record_number(selected_factor_row.get("cagr")),
                    "sharpe": _record_number(selected_factor_row.get("sharpe")),
                    "maxDrawdown": _record_number(selected_factor_row.get("max_drawdown")),
                    "annualizedTurnover": _record_number(
                        selected_factor_row.get("annualized_turnover")
                    ),
                    "annualizedCostDrag": _record_number(
                        selected_factor_row.get("annualized_cost_drag")
                    ),
                    "maximumSecurityDayContribution": _record_number(
                        selected_factor_row.get("max_abs_security_day_contribution")
                    ),
                    "maximumSecurityAbsoluteContributionShare": _record_number(
                        selected_factor_row.get("max_security_absolute_contribution_share")
                    ),
                    "maximumLeaveOneSecurityCagrDelta": _record_number(
                        selected_factor_row.get("max_abs_leave_one_security_cagr_delta")
                    ),
                },
                "currentPortfolioValidation": current_summaries[policy_id],
            }
        )
    return rows


def main() -> int:
    args = _parser().parse_args()
    if args.symbols < MINIMUM_SCALE_SYMBOLS:
        raise ValueError(
            f"large-scale contract requires at least {MINIMUM_SCALE_SYMBOLS} candidate symbols"
        )
    _reject_public_output_paths(args)
    config = RunConfig(
        demo=True,
        demo_symbol_count=args.symbols,
        demo_seed=args.seed,
        demo_missing_ratio=args.missing_ratio,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        site_dir=args.site_dir,
    )
    started = time.perf_counter()
    result = run_analysis(config)
    result_path = write_result_json(result)
    site_paths = write_dashboard_site(result, config.site_dir)
    payload = result_payload(result)

    validation_failures = _validate_payload_contract(payload, args=args, config=config)
    current_failures, current_summaries, checked_current_portfolios = (
        _recompute_all_current_portfolios(result, payload)
    )
    validation_failures.extend(current_failures)

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ranking = payload["factorPolicyRanking"]
    selected_row = next(row for row in ranking if row["selected"] is True)
    selected_portfolio = payload["currentResearchTarget"]
    status_counts = Counter(str(row["comparison_status"]) for row in ranking)
    reason_counts: Counter[str] = Counter()
    for row in ranking:
        reason_counts.update(str(code) for code in row.get("exclusion_reason_codes", []))
    candidates = result.market_data.candidate_symbols
    candidate_prices = result.market_data.prices.loc[:, candidates]
    candidate_cells_excluding_final = max(1, (len(candidate_prices.index) - 1) * len(candidates))
    missing_cells = int(candidate_prices.iloc[:-1].isna().to_numpy().sum())
    final_missing_cells = int(candidate_prices.iloc[-1].isna().sum())
    realized_missing_ratio = missing_cells / candidate_cells_excluding_final
    if args.missing_ratio == 0.0 and missing_cells != 0:
        validation_failures.append("fixture:clean_case_contains_missing_candidate_prices")
    if args.missing_ratio and realized_missing_ratio < args.missing_ratio:
        validation_failures.append("fixture:realized_missing_ratio_below_request")
    if final_missing_cells != 0:
        validation_failures.append("fixture:final_candidate_quotes_missing")

    session_count = int(payload["data"]["observations"])
    pre_evaluation_sessions = session_count - config.evaluation_window_days
    if pre_evaluation_sessions < LONGEST_RAW_SIGNAL_FORMATION_SESSIONS:
        validation_failures.append("fixture:insufficient_pre_evaluation_signal_formation")
    available_rows = [row for row in ranking if row["comparison_status"] == "available"]
    minimum_grid_observations = min(float(row["observations"]) for row in available_rows)
    minimum_grid_daily_risk_observations = min(
        float(row["daily_risk_observations"]) for row in available_rows
    )
    wall_seconds = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_SELF)
    harness_max_rss_bytes = _max_rss_bytes(usage)
    report = {
        "validationStatus": "passed" if not validation_failures else "failed",
        "purpose": "deterministic_synthetic_scale_and_contract_validation_only",
        "syntheticStress": True,
        "actualMarketEvidence": False,
        "publicationAllowed": False,
        "warning": (
            "This 2701+-symbol dataset is deterministic synthetic test data. It validates scale, "
            "schema, accounting, policy-grid, and portfolio invariants only; it is not a current "
            "market result and must not replace a failed or unavailable live-market run."
        ),
        "stressMode": "sparse_missing" if args.missing_ratio else "clean",
        "config": {
            "symbols": args.symbols,
            "startDate": args.start_date,
            "endDate": args.end_date,
            "seed": args.seed,
            "requestedMissingRatio": args.missing_ratio,
            "unchangedGuardrails": {
                "evaluationWindowDays": config.evaluation_window_days,
                "minimumEvaluationObservations": config.min_evaluation_observations,
                "minimumDailyRiskObservations": config.min_daily_risk_observations,
                "minimumValuationCoverage": config.min_valuation_coverage,
                "longestRawPriceFormulaFormationSessions": (LONGEST_RAW_SIGNAL_FORMATION_SESSIONS),
                "minimumHistoryDays": config.min_history_days,
                "topN": config.top_n,
                "maximumWeight": config.max_weight,
                "totalCostBps": config.total_cost_bps,
            },
            "periodRationale": (
                f"{session_count} deterministic business-day sessions leave "
                f"{pre_evaluation_sessions} sessions before the unchanged "
                f"{config.evaluation_window_days}-session evaluation window. This exceeds the "
                f"longest {LONGEST_RAW_SIGNAL_FORMATION_SESSIONS}-session raw-price formula "
                f"formation window. Eligibility-aware factors retain at least "
                f"{minimum_grid_observations:.0f} evaluated observations and "
                f"{minimum_grid_daily_risk_observations:.0f} exact daily-risk observations, above "
                f"the unchanged {config.min_evaluation_observations} evaluation and "
                f"{config.min_daily_risk_observations} daily-risk guardrails, "
                "while avoiding the unnecessary late-2023 tail in the previous default."
            ),
        },
        "result": {
            "schemaVersion": payload["schemaVersion"],
            "dataMode": payload["data"]["mode"],
            "synthetic": payload["data"]["synthetic"],
            "dataAsOf": payload["data"]["asOf"],
            "sessionCount": session_count,
            "preEvaluationSessions": pre_evaluation_sessions,
            "requestedCandidateCount": payload["data"]["requestedCandidateCount"],
            "providerReturnedCandidateCount": payload["data"]["providerReturnedCandidateCount"],
            "inputSecurityCount": payload["data"]["inputSecurityCount"],
            "analyzedSecurityCount": payload["data"]["analyzedSecurityCount"],
            "eligibleSecurityCount": payload["data"]["latestEligibleSecurityCount"],
            "factorCount": payload["meta"]["factorCount"],
            "independentFactorCount": payload["meta"]["independentFactorCount"],
            "aliasFactorCount": payload["meta"]["aliasFactorCount"],
            "availableIndependentPairCount": payload["meta"]["availableIndependentPairCount"],
            "excludedIndependentPairCount": payload["meta"]["excludedIndependentPairCount"],
            "policyCount": payload["meta"]["policyCount"],
            "policyFactorRunCount": payload["meta"]["policyFactorRunCount"],
            "resultKey": payload["resultKey"],
            "resultIdentity": payload["resultIdentity"],
            "selectedPolicy": payload["selectedWeightingPolicy"],
            "selectedFactor": payload["selectedFactor"],
            "selectedJointReason": payload["selectedReason"],
            "selectedBaseCompositeScore": selected_row["base_composite_score"],
            "selectedSelectionScore": selected_row["selection_score"],
            "selectedAbsoluteGuardrailPass": selected_row["absolute_guardrail_pass"],
            "selectedSelectionStatus": selected_row["selection_status"],
            "selectedObservations": selected_row["observations"],
            "selectedDailyRiskObservations": selected_row["daily_risk_observations"],
            "selectedValuationCoverageRatio": selected_row["valuation_coverage_ratio"],
            "selectedHoldingCount": selected_portfolio["selectedSecurityCount"],
            "selectedCashWeight": selected_portfolio["cashWeight"],
            "selectedConcentration": selected_portfolio["concentration"],
            "contributionDiagnostics": payload["contributionDiagnostics"],
            "gridAccounting": payload["gridAccounting"],
            "currentTransition": payload["currentTransition"],
        },
        "policyResults": _policy_report_rows(payload, current_summaries),
        "factorPolicyStatusCounts": dict(sorted(status_counts.items())),
        "factorPolicyExclusionReasonCounts": dict(sorted(reason_counts.items())),
        "currentPortfolioValidation": {
            "expectedPortfolioCount": EXPECTED_POLICY_FACTOR_RUN_COUNT,
            "checkedPortfolioCount": checked_current_portfolios,
            "serializedCurrentResearchTargetCount": 1,
            "serializedCurrentRankingRowCount": len(ranking),
            "reconciledCurrentRankingRowCount": checked_current_portfolios,
            "reconciledCurrentRankingFields": [
                "current_portfolio_available",
                "current_holding_count",
                "current_cash_weight",
                "current_target_effective_names",
                "current_target_hhi",
                "current_target_max_weight",
                "current_portfolio_input_reasons",
                "guardrail_current_target",
                "guardrail_current_effective_names",
                "guardrail_current_target_hhi",
                "guardrail_current_target_weight",
            ],
            "failureCount": len(current_failures),
            "failures": current_failures,
        },
        "jointFactorPolicyGridValidation": {
            "expectedRunCount": EXPECTED_POLICY_FACTOR_RUN_COUNT,
            "observedRunCount": len(ranking),
            "expectedIndependentPairCount": EXPECTED_INDEPENDENT_PAIR_COUNT,
            "expectedAliasPairCount": EXPECTED_ALIAS_PAIR_COUNT,
            "accounting": payload["gridAccounting"],
            "minimumObservedEvaluationObservations": minimum_grid_observations,
            "minimumObservedDailyRiskObservations": minimum_grid_daily_risk_observations,
        },
        "missingness": {
            "candidateMissingCellsExcludingFinalDate": missing_cells,
            "realizedMissingRatioExcludingFinalDate": realized_missing_ratio,
            "finalCandidateMissingCells": final_missing_cells,
        },
        "validationFailures": validation_failures,
        "performance": {
            "analysisWallSeconds": result.runtime_seconds,
            "harnessWallSeconds": wall_seconds,
            "analysisPeakRssBytes": result.max_rss_bytes,
            "analysisPeakRssMiB": result.max_rss_bytes / 1024**2,
            "harnessPeakRssBytes": harness_max_rss_bytes,
            "harnessPeakRssMiB": harness_max_rss_bytes / 1024**2,
            "swapOperations": int(getattr(usage, "ru_nswap", 0)),
            "swapUsed": bool(getattr(usage, "ru_nswap", 0)),
            "payloadBytes": len(encoded),
            "resultJsonBytes": result_path.stat().st_size,
            "dashboardJsonBytes": Path(site_paths["data"]).stat().st_size,
            "summaryJsonBytes": Path(site_paths["summary"]).stat().st_size,
        },
        "provenance": {
            "inputSha256": payload["data"]["inputSha256"],
            "factorDefinitionSha256": payload["meta"]["factorDefinitionSha256"],
            "policyDefinitionSha256": payload["meta"]["policyDefinitionSha256"],
            "selectionSpecSha256": payload["meta"]["selectionSpecSha256"],
            "resultIdentity": payload["resultIdentity"],
            "generatorLabel": payload["data"]["sourceLabel"],
            "researchEvidenceStatus": payload["researchScope"]["evidenceStatus"],
        },
        "paths": {"result": str(result_path), **site_paths, "report": str(args.report)},
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False))
    if validation_failures:
        raise RuntimeError(
            f"large-scale validation failed with {len(validation_failures)} issue(s); "
            f"see {args.report}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
