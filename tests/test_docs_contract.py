import json
from pathlib import Path

from momentum_factor_lab.cli import LEGACY_SCHEDULED_ARGUMENTS, build_parser

ROOT = Path(__file__).resolve().parents[1]


def _published_actual_grid() -> list[tuple[dict[str, object], dict[str, object]]]:
    grid_root = ROOT / "docs" / "data" / "grid" / "v1"
    manifest = json.loads((grid_root / "manifest.json").read_text(encoding="utf-8"))
    entries: list[tuple[dict[str, object], dict[str, object]]] = []
    for entry in manifest["entries"]:
        detail = json.loads((grid_root / entry["detail"]["path"]).read_text(encoding="utf-8"))
        assert detail["data"]["mode"] == "live_market"
        assert detail["data"]["synthetic"] is False
        assert detail["data"]["analyzedSecurityCount"] >= 2_700
        entries.append((entry, detail))
    return entries


def _input_differences(left: dict[str, object], right: dict[str, object]) -> set[str]:
    return {key for key in set(left) | set(right) if left.get(key) != right.get(key)}


def _allocation_signature(
    detail: dict[str, object],
) -> tuple[tuple[str, ...], tuple[tuple[str, float], ...]]:
    weights = detail["currentResearchTarget"]["weights"]
    return (
        tuple(row["symbol"] for row in weights),
        tuple((row["symbol"], round(float(row["weight"]), 12)) for row in weights),
    )


def test_published_actual_grid_regresses_web_input_and_market_asof_outcome_changes() -> None:
    entries = _published_actual_grid()
    observed_changes: set[str] = set()
    web_input_comparisons = 0
    market_asof_comparisons = 0

    for index, (left_entry, left) in enumerate(entries):
        for right_entry, right in entries[index + 1 :]:
            differences = _input_differences(
                left_entry["normalizedInputs"],
                right_entry["normalizedInputs"],
            )
            left_symbols, left_weights = _allocation_signature(left)
            right_symbols, right_weights = _allocation_signature(right)

            if differences == {"top_n"}:
                web_input_comparisons += 1
                assert left["selectedFactor"] != right["selectedFactor"]
                assert left["selectedWeightingPolicy"] != right["selectedWeightingPolicy"]
                assert left_symbols != right_symbols
                assert left_weights != right_weights
                observed_changes.update({"factor", "policy", "holdings", "weights"})

            if differences == {"end_date", "effective_end_date"}:
                market_asof_comparisons += 1
                assert left["data"]["asOf"] != right["data"]["asOf"]
                assert left_symbols != right_symbols
                assert left_weights != right_weights
                observed_changes.update({"holdings", "weights"})

    assert web_input_comparisons >= 1
    assert market_asof_comparisons >= 1
    assert observed_changes == {"factor", "policy", "holdings", "weights"}


def test_readme_declares_the_live_2700_factor_and_policy_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()

    required = (
        "2,700개 이상",
        "64개 팩터",
        "61개 독립 팩터",
        "compatibility alias 3개",
        "equal_weight",
        "capped_linear_rank",
        "capped_vol_adjusted_rank",
        "score_liquidity_rank",
        "live_market",
        "local_file",
        "demo",
        "61 × 4 = 244",
        "256개 전체 factor-policy 행",
        "one-way turnover",
        "schema-v4",
        "result identity",
        "로컬 api",
    )
    for text in required:
        assert text.lower() in readme
    assert "demo는 테스트 전용" in readme
    assert "실제시장 수집 실패를 demo나 기존 정적 결과로 대체하지 않습니다" in readme
    assert "다음 세션 종가용 연구 목표" in readme


def test_methodology_matches_the_current_shared_kernel_research_contract() -> None:
    methodology = (ROOT / "docs/methodology.md").read_text(encoding="utf-8").lower()

    required = (
        "2,700",
        "64",
        "61",
        "alias",
        "equal_weight",
        "capped_linear_rank",
        "capped_vol_adjusted_rank",
        "score_liquidity_rank",
        "244",
        "factorpolicyranking",
        "cash",
        "turnover",
        "schema v4",
        "currentresearchtarget",
        "resultidentity",
        "leave-one",
    )
    for text in required:
        assert text in methodology

    forbidden_legacy_contracts = (
        "recommendations",
        "research_signals",
        "--factor-selection-mode",
        "--frozen-policy-path",
        "--target-aum",
        "--max-adv-participation",
        "pdf",
        "excel",
        "xlsx",
    )
    for text in forbidden_legacy_contracts:
        assert text not in methodology


def test_factor_catalog_documents_all_64_factors_and_alias_status() -> None:
    catalog = (ROOT / "docs/factor-catalog.md").read_text(encoding="utf-8").lower()

    assert "total factors: **64**" in catalog
    assert "independent selection-eligible factors: **61**" in catalog
    assert "compatibility aliases: **3**" in catalog
    assert "`volume_confirmed_mom_6m`" in catalog
    assert "`signed_volume_pressure_3m`" in catalog
    assert "`acceleration`" in catalog
    assert "`short_acceleration`" in catalog
    assert "`relative_strength_6m`" in catalog


def test_scheduled_dashboard_config_parses_as_uncapped_live_input() -> None:
    config_path = ROOT / ".github/momentum-dashboard-config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    run_args = payload["run_args"]
    namespace = build_parser().parse_args(["run", *run_args])
    supplied_flags = {
        item.split("=", maxsplit=1)[0]
        for item in run_args
        if isinstance(item, str) and item.startswith("--")
    }

    assert namespace.command == "run"
    assert namespace.live is True
    assert namespace.demo is False
    assert namespace.prices is None
    assert namespace.max_price_symbols is None
    assert namespace.export_input_snapshot is True
    assert not supplied_flags.intersection(LEGACY_SCHEDULED_ARGUMENTS)
    assert "--demo" not in supplied_flags
    assert "--max-price-symbols" not in supplied_flags


def test_daily_workflow_runs_freshness_and_monotonic_schema_gates() -> None:
    workflow = (ROOT / ".github/workflows/daily-dashboard.yml").read_text(encoding="utf-8")

    assert "momentum_factor_lab.dashboard_freshness" in workflow
    assert "momentum_factor_lab.dashboard_monotonic" in workflow
    assert "momentum_factor_lab.cli scheduled-dashboard" in workflow
    assert "--data-path docs/data/dashboard.json" in workflow
    assert "git add docs" in workflow
