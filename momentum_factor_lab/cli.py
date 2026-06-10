from __future__ import annotations

import argparse
import contextlib
import io
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .dashboard import DEFAULT_SITE_TITLE, write_dashboard_site
from .config import RunConfig
from .report import write_reports
from .universe import normalize_symbols
from .workflow import _json_safe, run_analysis

RUN_DEFAULTS: dict[str, Any] = {
    "start_date": "2016-01-01",
    "end_date": None,
    "output_dir": "outputs/sample",
    "report_dir": "reports/sample",
    "cache_dir": ".cache/momentum_factor_lab",
    "universe": None,
    "universe_source_mode": "packaged",
    "universe_profile": "large_liquid",
    "top_n": 20,
    "max_weight": 0.10,
    "recommendation_weighting_method": "score_size_liquidity",
    "recommendation_score_weight": 0.60,
    "recommendation_market_cap_weight": 0.25,
    "recommendation_liquidity_weight": 0.15,
    "recommendation_rank_floor": 0.05,
    "disable_recommendation_market_cap_lookup": False,
    "max_price_symbols": None,
    "price_chunk_size": 150,
    "stooq_fallback_limit": None,
    "finance_datareader_fallback_limit": None,
    "retry_count": 1,
    "retry_backoff_seconds": 0.5,
    "cost_stress_high_bps": 50.0,
    "sec_user_agent": None,
    "min_price": 5.0,
    "min_avg_dollar_volume": 5_000_000.0,
    "min_avg_volume": 0.0,
    "min_history_days": 252,
    "min_liquidity_observations": 63,
    "data_quality_lookback_days": 252,
    "max_price_missing_ratio": 0.05,
    "max_volume_missing_ratio": 0.10,
    "max_extreme_daily_return": 0.80,
    "target_aum": None,
    "max_adv_participation": None,
    "selected_factor": None,
    "factor_selection_mode": "research_validation",
    "selection_window": "validation_split_70_30",
    "frozen_policy_path": None,
    "point_in_time_universe_provenance": None,
    "approved_tradable_universe": False,
    "min_tradable_universe_size": 2_000,
    "json": False,
}


class WizardAbort(RuntimeError):
    """Raised when the interactive wizard is intentionally aborted."""


def _add_run_arguments(run: argparse.ArgumentParser) -> None:
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--offline-sample", action="store_true", help="Use deterministic offline sample data")
    mode.add_argument("--live", action="store_true", help="Try live yfinance/Stooq free/public data")
    run.add_argument("--start-date", default=RUN_DEFAULTS["start_date"])
    run.add_argument("--end-date", default=RUN_DEFAULTS["end_date"])
    run.add_argument("--output-dir", default=RUN_DEFAULTS["output_dir"])
    run.add_argument("--report-dir", default=RUN_DEFAULTS["report_dir"])
    run.add_argument("--cache-dir", default=RUN_DEFAULTS["cache_dir"])
    run.add_argument("--universe", default=RUN_DEFAULTS["universe"], help="Comma-separated symbols; omitted uses packaged 2,000+ universe")
    run.add_argument("--universe-source-mode", choices=["packaged", "refresh"], default=RUN_DEFAULTS["universe_source_mode"])
    run.add_argument(
        "--universe-profile",
        choices=["large_liquid", "extended_current", "aggressive_stock_only"],
        default=RUN_DEFAULTS["universe_profile"],
        help="Candidate-universe profile; missing PIT evidence is reported as an execution limitation.",
    )
    run.add_argument("--top-n", type=int, default=RUN_DEFAULTS["top_n"])
    run.add_argument("--max-weight", type=float, default=RUN_DEFAULTS["max_weight"])
    run.add_argument(
        "--recommendation-weighting-method",
        choices=["equal", "score_size_liquidity"],
        default=RUN_DEFAULTS["recommendation_weighting_method"],
        help="Current recommendation weighting method; backtests remain comparable capped top-N portfolios",
    )
    run.add_argument("--recommendation-score-weight", type=float, default=RUN_DEFAULTS["recommendation_score_weight"])
    run.add_argument("--recommendation-market-cap-weight", type=float, default=RUN_DEFAULTS["recommendation_market_cap_weight"])
    run.add_argument("--recommendation-liquidity-weight", type=float, default=RUN_DEFAULTS["recommendation_liquidity_weight"])
    run.add_argument("--recommendation-rank-floor", type=float, default=RUN_DEFAULTS["recommendation_rank_floor"])
    run.add_argument(
        "--disable-recommendation-market-cap-lookup",
        action="store_true",
        default=RUN_DEFAULTS["disable_recommendation_market_cap_lookup"],
        help="Disable best-effort yfinance market-cap enrichment for final recommendation candidates",
    )
    run.add_argument("--max-price-symbols", type=int, default=RUN_DEFAULTS["max_price_symbols"], help="Optional live/smoke cap; reports are marked subset when used")
    run.add_argument("--price-chunk-size", type=int, default=RUN_DEFAULTS["price_chunk_size"])
    run.add_argument(
        "--stooq-fallback-limit",
        type=int,
        default=RUN_DEFAULTS["stooq_fallback_limit"],
        help="Maximum missing symbols to retry through Stooq; omitted retries all missing symbols, 0 disables",
    )
    run.add_argument(
        "--finance-datareader-fallback-limit",
        type=int,
        default=RUN_DEFAULTS["finance_datareader_fallback_limit"],
        help="Maximum still-missing symbols to retry through optional FinanceDataReader; omitted retries all, 0 disables",
    )
    run.add_argument("--retry-count", type=int, default=RUN_DEFAULTS["retry_count"])
    run.add_argument("--retry-backoff-seconds", type=float, default=RUN_DEFAULTS["retry_backoff_seconds"])
    run.add_argument("--cost-stress-high-bps", type=float, default=RUN_DEFAULTS["cost_stress_high_bps"])
    run.add_argument(
        "--sec-user-agent",
        default=RUN_DEFAULTS["sec_user_agent"],
        help="SEC EDGAR User-Agent/contact string; can also be set with MOMENTUM_FACTOR_LAB_SEC_USER_AGENT.",
    )
    run.add_argument("--min-price", type=float, default=RUN_DEFAULTS["min_price"])
    run.add_argument("--min-avg-dollar-volume", type=float, default=RUN_DEFAULTS["min_avg_dollar_volume"])
    run.add_argument("--min-avg-volume", type=float, default=RUN_DEFAULTS["min_avg_volume"])
    run.add_argument("--min-history-days", type=int, default=RUN_DEFAULTS["min_history_days"])
    run.add_argument(
        "--min-liquidity-observations",
        type=int,
        default=RUN_DEFAULTS["min_liquidity_observations"],
        help="Minimum non-null price/volume/dollar-volume observations required in the 63-day liquidity window",
    )
    run.add_argument(
        "--data-quality-lookback-days",
        type=int,
        default=RUN_DEFAULTS["data_quality_lookback_days"],
        help="Recent trading-day lookback used for per-symbol data-quality diagnostics",
    )
    run.add_argument(
        "--max-price-missing-ratio",
        type=float,
        default=RUN_DEFAULTS["max_price_missing_ratio"],
        help="Maximum recent missing-price ratio before a symbol fails data-quality checks",
    )
    run.add_argument(
        "--max-volume-missing-ratio",
        type=float,
        default=RUN_DEFAULTS["max_volume_missing_ratio"],
        help="Maximum recent volume-missing ratio before a symbol fails data-quality checks",
    )
    run.add_argument(
        "--max-extreme-daily-return",
        type=float,
        default=RUN_DEFAULTS["max_extreme_daily_return"],
        help="Maximum absolute adjusted daily return before flagging a data-quality anomaly",
    )
    run.add_argument("--target-aum", type=float, default=RUN_DEFAULTS["target_aum"], help="Target AUM used for capacity diagnostics")
    run.add_argument(
        "--max-adv-participation",
        type=float,
        default=RUN_DEFAULTS["max_adv_participation"],
        help="Maximum share of 63-day ADV a target position may consume before capacity is flagged",
    )
    run.add_argument(
        "--selected-factor",
        default=RUN_DEFAULTS["selected_factor"],
        help=(
            "Frozen/predeclared factor override for practical output. Must be paired with "
            "--factor-selection-mode predeclared; otherwise validation/walk-forward selections stay research-only."
        ),
    )
    run.add_argument(
        "--factor-selection-mode",
        choices=["research_validation", "predeclared", "walk_forward"],
        default=RUN_DEFAULTS["factor_selection_mode"],
        help="How the selected factor is controlled for anti-overfit gating.",
    )
    run.add_argument("--selection-window", default=RUN_DEFAULTS["selection_window"])
    run.add_argument("--frozen-policy-path", default=RUN_DEFAULTS["frozen_policy_path"])
    run.add_argument(
        "--point-in-time-universe-provenance",
        default=RUN_DEFAULTS["point_in_time_universe_provenance"],
        help="Explicit provenance/attestation for point-in-time universe evidence; missing evidence is reported as a limitation.",
    )
    run.add_argument(
        "--approved-tradable-universe",
        action="store_true",
        default=RUN_DEFAULTS["approved_tradable_universe"],
        help="Attest that a user-supplied small universe is an approved tradable universe; missing PIT/capacity evidence remains visible.",
    )
    run.add_argument("--min-tradable-universe-size", type=int, default=RUN_DEFAULTS["min_tradable_universe_size"])
    run.add_argument("--json", action="store_true", default=RUN_DEFAULTS["json"], help="Emit machine-readable summary")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Momentum Factor Lab analysis.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run factor comparison and report generation")
    _add_run_arguments(run)
    wizard = sub.add_parser(
        "wizard",
        aliases=["run-wizard", "interactive"],
        help="Interactively configure run inputs with descriptions, defaults, and validation",
    )
    wizard.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip the final confirmation prompt after interactive inputs are collected",
    )
    dashboard = sub.add_parser("dashboard", help="Build the Korean static dashboard site from run-results JSON")
    dashboard.add_argument(
        "--run-results",
        nargs="+",
        required=True,
        help="One or more run_results_*.json paths or globs. Quote globs for cross-shell portability.",
    )
    dashboard.add_argument("--site-dir", default="docs", help="Directory where the static site will be written")
    dashboard.add_argument("--title", default=DEFAULT_SITE_TITLE, help="Korean dashboard page title")
    dashboard.add_argument("--history-limit", type=int, default=60, help="Maximum dashboard runs to retain")
    dashboard.add_argument("--json", action="store_true", help="Emit generated site paths as JSON")

    scheduled = sub.add_parser(
        "scheduled-dashboard",
        help="Run analysis from a saved config and rebuild the GitHub Pages dashboard",
    )
    scheduled.add_argument(
        "--config",
        default=".github/momentum-dashboard-config.json",
        help="JSON config containing run_args and optional site_dir/title",
    )
    scheduled.add_argument("--site-dir", default=None, help="Override dashboard output directory")
    scheduled.add_argument("--title", default=None, help="Override dashboard title")
    scheduled.add_argument("--history-limit", type=int, default=None, help="Override maximum retained dashboard runs")
    scheduled.add_argument("--json", action="store_true", help="Emit generated site paths as JSON")
    return parser


def config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=Path(args.output_dir),
        report_dir=Path(args.report_dir),
        cache_dir=Path(args.cache_dir),
        offline_sample=not args.live,
        universe=normalize_symbols(args.universe),
        universe_source_mode=args.universe_source_mode,
        universe_profile=args.universe_profile,
        top_n=args.top_n,
        max_weight=args.max_weight,
        recommendation_weighting_method=args.recommendation_weighting_method,
        recommendation_score_weight=args.recommendation_score_weight,
        recommendation_market_cap_weight=args.recommendation_market_cap_weight,
        recommendation_liquidity_weight=args.recommendation_liquidity_weight,
        recommendation_rank_floor=args.recommendation_rank_floor,
        recommendation_market_cap_lookup=not args.disable_recommendation_market_cap_lookup,
        max_price_symbols=args.max_price_symbols,
        price_chunk_size=args.price_chunk_size,
        stooq_fallback_limit=args.stooq_fallback_limit,
        finance_datareader_fallback_limit=args.finance_datareader_fallback_limit,
        retry_count=args.retry_count,
        retry_backoff_seconds=args.retry_backoff_seconds,
        cost_stress_high_bps=args.cost_stress_high_bps,
        sec_user_agent=args.sec_user_agent,
        min_price=args.min_price,
        min_avg_dollar_volume=args.min_avg_dollar_volume,
        min_avg_volume=args.min_avg_volume,
        min_history_days=args.min_history_days,
        min_liquidity_observations=args.min_liquidity_observations,
        factor_selection_mode=args.factor_selection_mode,
        selection_window=args.selection_window,
        frozen_policy_path=Path(args.frozen_policy_path) if args.frozen_policy_path else None,
        selected_factor=args.selected_factor,
        target_aum=args.target_aum,
        max_adv_participation=args.max_adv_participation,
        point_in_time_universe_provenance=args.point_in_time_universe_provenance,
        approved_tradable_universe=args.approved_tradable_universe,
        min_tradable_universe_size=args.min_tradable_universe_size,
        data_quality_lookback_days=args.data_quality_lookback_days,
        max_price_missing_ratio=args.max_price_missing_ratio,
        max_volume_missing_ratio=args.max_volume_missing_ratio,
        max_extreme_daily_return=args.max_extreme_daily_return,
    )


def _print_summary(summary: dict[str, object], result: object, output_key: str) -> None:
    print(f"Selected factor: {summary['selected_factor']}")
    print(f"Output status: {summary['recommendation_status']}")
    print(f"Output type: {summary['recommendation_output']}")
    print(f"Fresh live data available: {summary['fresh_live_data_available']}")
    limitations = summary["execution_limitations"]
    print(f"Execution limitations: {', '.join(limitations) if limitations else 'none'}")
    print(f"Liquidity/capacity: {summary['recommendation_capacity_warning']}")
    cash_weight = summary["recommendation_cash_weight"]
    cash_text = f"{cash_weight:.2%}" if isinstance(cash_weight, int | float) else "unavailable"
    print(f"Output-row weighting policy: {summary['recommendation_weighting_method']} (cash remainder {cash_text})")
    if summary.get("fail_closed"):
        print("Research-only fail-closed: tradable/proposed weights are forced to zero.")
    print(f"Data as of: {summary['data_as_of']} via {summary['provider']}")
    print(
        "Universe: "
        f"{summary['candidate_universe_size']} candidates; "
        f"{summary['eligible_price_universe_size']} eligible price symbols; "
        f"{summary['factor_count']} factors; validation {summary['factor_validation_status']}"
    )
    print("Outputs:")
    for key, value in result.output_paths.items():
        print(f"  {key}: {value}")
    print(f"Top {output_key.replace('_', ' ')}:")
    print(result.recommendations.head(result.config.top_n).to_string(index=False))


def execute_config(config: RunConfig, *, emit_json: bool = False) -> dict[str, object]:
    result = write_reports(run_analysis(config))
    output_key = result.metadata["recommendation_output_key"]
    summary = {
        "selected_factor": result.selected_factor,
        "recommendation_status": result.metadata["recommendation_status"],
        "current_recommendations_available": result.metadata["current_recommendations_available"],
        "fresh_live_data_available": result.metadata["fresh_live_data_available"],
        "recommendation_output": result.metadata["recommendation_output_label"],
        "data_as_of": result.metadata["data_as_of"],
        "provider": result.metadata["provider"],
        "candidate_universe_size": result.metadata["candidate_universe_size"],
        "eligible_price_universe_size": result.metadata["eligible_price_universe_size"],
        "factor_count": result.metadata["factor_count"],
        "factor_validation_status": result.metadata["factor_validation_status"],
        "universe_profile": result.metadata["universe_profile"],
        "factor_selection_mode": result.metadata["factor_selection_mode"],
        "selected_factor_selection_source": result.metadata["selected_factor_selection_source"],
        "same_sample_selection_blocked_for_tradable": result.metadata["same_sample_selection_blocked_for_tradable"],
        "same_run_factor_selection_blocked_for_tradable": result.metadata.get(
            "same_run_factor_selection_blocked_for_tradable",
            result.metadata["same_sample_selection_blocked_for_tradable"],
        ),
        "decision_support_tier": result.metadata["decision_support_tier"],
        "fail_closed": result.metadata["fail_closed"],
        "fail_closed_reasons": result.metadata.get("fail_closed_reasons", []),
        "tradability_blockers": result.metadata.get("tradability_blockers", []),
        "execution_limitations": result.metadata.get("execution_limitations", []),
        "data_quality_gate": result.metadata.get("data_quality_gate", {}),
        "data_quality_status_counts": result.metadata.get("data_quality_status_counts", {}),
        "recommendation_data_quality_status_counts": result.metadata.get("recommendation_data_quality_status_counts", {}),
        "recommendation_capacity_warning": result.metadata.get("recommendation_capacity_warning"),
        "recommendation_weighting_method": result.metadata.get("recommendation_weighting_method"),
        "recommendation_weight_sum": result.metadata.get("recommendation_weight_sum"),
        "recommendation_cash_weight": result.metadata.get("recommendation_cash_weight"),
        "outputs": result.output_paths,
        f"top_{output_key}": result.recommendations.head(result.config.top_n).to_dict(orient="records"),
    }
    if emit_json:
        summary = _json_safe(summary)
        print(json.dumps(summary, indent=2, allow_nan=False))
    else:
        _print_summary(summary, result, output_key)
    return summary


def run_command(args: argparse.Namespace) -> dict[str, object]:
    return execute_config(config_from_args(args), emit_json=args.json)


def _format_default(value: object) -> str:
    if value is None:
        return "blank / none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _prompt_raw(label: str, description: str, default: object, extra: str | None = None) -> str:
    print(f"\n{label}")
    print(f"  {description}")
    if extra:
        print(f"  {extra}")
    print(f"  Default [{_format_default(default)}]")
    try:
        return input("  > ").strip()
    except (EOFError, KeyboardInterrupt) as exc:  # pragma: no cover - interactive signal path
        raise WizardAbort("interactive wizard aborted before execution") from exc


def _ask_value(
    label: str,
    description: str,
    default: Any,
    parser: Callable[[str], Any],
    validator: Callable[[Any], bool] | None = None,
    error: str = "invalid value",
    extra: str | None = None,
) -> Any:
    while True:
        raw = _prompt_raw(label, description, default, extra)
        if raw == "":
            return default
        try:
            value = parser(raw)
        except ValueError:
            print(f"  Error: {error}")
            continue
        if validator is not None and not validator(value):
            print(f"  Error: {error}")
            continue
        return value


def _ask_optional(
    label: str,
    description: str,
    default: Any,
    parser: Callable[[str], Any],
    validator: Callable[[Any], bool] | None = None,
    error: str = "invalid value",
    extra: str | None = None,
) -> Any:
    while True:
        raw = _prompt_raw(label, description, default, extra)
        if raw == "":
            return default
        if raw.lower() in {"none", "null", "blank"}:
            return None
        try:
            value = parser(raw)
        except ValueError:
            print(f"  Error: {error}")
            continue
        if validator is not None and not validator(value):
            print(f"  Error: {error}")
            continue
        return value


def _parse_iso_date(value: str) -> str:
    datetime.fromisoformat(value).date()
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"y", "yes", "true", "1", "on"}:
        return True
    if normalized in {"n", "no", "false", "0", "off"}:
        return False
    raise ValueError("expected yes/no")


def _ask_bool(label: str, description: str, default: bool) -> bool:
    return bool(
        _ask_value(
            label,
            description,
            default,
            _parse_bool,
            error="enter yes/no, y/n, true/false, or 1/0",
        )
    )


def _ask_choice(label: str, description: str, default: str, choices: list[str]) -> str:
    choices_text = ", ".join(f"{i + 1}={choice}" for i, choice in enumerate(choices))

    def parse_choice(value: str) -> str:
        text = value.strip()
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(choices):
                return choices[index]
        lowered = text.lower()
        for choice in choices:
            if lowered == choice.lower():
                return choice
        raise ValueError("invalid choice")

    return str(
        _ask_value(
            label,
            description,
            default,
            parse_choice,
            error=f"choose one of: {', '.join(choices)}",
            extra=f"Choices: {choices_text}",
        )
    )


def _wizard_namespace() -> argparse.Namespace:
    values = dict(RUN_DEFAULTS)
    print("Momentum Factor Lab interactive run wizard")
    print("Press Enter to keep a default. Type 'none' for optional blank values.")

    mode = _ask_choice(
        "Data mode",
        "Use deterministic offline sample data for fast/reproducible tests, or live free/public market data.",
        "offline_sample",
        ["offline_sample", "live"],
    )
    values["live"] = mode == "live"
    values["offline_sample"] = not values["live"]
    values["start_date"] = _ask_value(
        "Start date",
        "First analysis date in ISO format. Affects downloaded prices, factor lookbacks, and backtests.",
        values["start_date"],
        _parse_iso_date,
        error="enter an ISO date such as 2016-01-01",
    )
    values["end_date"] = _ask_optional(
        "End date",
        "Inclusive analysis end date. Blank lets the run use its current effective date.",
        values["end_date"],
        _parse_iso_date,
        error="enter an ISO date such as 2026-06-08, or blank/none",
    )
    values["top_n"] = _ask_value(
        "Top-N holdings",
        "Number of highest-scoring stocks shown per rebalance; practical recommendations require tradability gates.",
        values["top_n"],
        int,
        lambda value: value >= 1,
        "enter an integer >= 1",
    )
    values["max_weight"] = _ask_value(
        "Max position weight",
        "Maximum weight for any one stock, as a decimal fraction. Example: 0.10 means 10%.",
        values["max_weight"],
        float,
        lambda value: 0 < value <= 1,
        "enter a decimal in (0, 1]",
    )
    values["output_dir"] = _ask_value(
        "Output directory",
        "Directory for canonical JSON run-result artifacts.",
        values["output_dir"],
        str,
        lambda value: bool(value.strip()),
        "enter a non-empty path",
    )
    values["report_dir"] = _ask_value(
        "Report directory",
        "Directory for generated PDF and Excel reports.",
        values["report_dir"],
        str,
        lambda value: bool(value.strip()),
        "enter a non-empty path",
    )
    values["cache_dir"] = _ask_value(
        "Cache directory",
        "Directory for downloaded universe/price/fundamental caches.",
        values["cache_dir"],
        str,
        lambda value: bool(value.strip()),
        "enter a non-empty path",
    )
    values["universe"] = _ask_optional(
        "Universe symbols",
        "Comma-separated candidate symbols. Blank uses the packaged broad stock-only universe.",
        values["universe"],
        str,
        lambda value: bool(value.strip()),
        "enter comma-separated symbols or blank/none",
    )
    values["universe_profile"] = _ask_choice(
        "Universe profile",
        "Controls the candidate stock profile used for live/public universe refresh and reporting limitations.",
        values["universe_profile"],
        ["large_liquid", "extended_current", "aggressive_stock_only"],
    )
    values["universe_source_mode"] = _ask_choice(
        "Universe source mode",
        "Use packaged metadata, or refresh public SEC/Nasdaq symbol metadata in live mode.",
        values["universe_source_mode"],
        ["packaged", "refresh"],
    )
    values["max_price_symbols"] = _ask_optional(
        "Max price symbols",
        "Optional live/smoke cap. Blank means no explicit cap.",
        values["max_price_symbols"],
        int,
        lambda value: value >= 1,
        "enter an integer >= 1 or blank/none",
    )
    values["target_aum"] = _ask_optional(
        "Target AUM",
        "Optional model-portfolio AUM for position capacity diagnostics.",
        values["target_aum"],
        float,
        lambda value: value > 0,
        "enter a positive number or blank/none",
    )
    values["max_adv_participation"] = _ask_optional(
        "Max ADV participation",
        "Optional maximum share of 63-day ADV a target position may consume. Example: 0.05 means 5%.",
        values["max_adv_participation"],
        float,
        lambda value: 0 < value <= 1,
        "enter a decimal in (0, 1] or blank/none",
    )
    values["min_price"] = _ask_value(
        "Minimum latest price",
        "Hard price floor for candidate eligibility and data-quality checks.",
        values["min_price"],
        float,
        lambda value: value >= 0,
        "enter a non-negative number",
    )
    values["min_avg_dollar_volume"] = _ask_value(
        "Minimum 63-day average dollar volume",
        "Liquidity floor used for eligibility and recommendation diagnostics.",
        values["min_avg_dollar_volume"],
        float,
        lambda value: value >= 0,
        "enter a non-negative number",
    )
    values["min_history_days"] = _ask_value(
        "Minimum price history days",
        "Minimum non-null price observations required before a stock can be eligible.",
        values["min_history_days"],
        int,
        lambda value: value >= 1,
        "enter an integer >= 1",
    )

    if _ask_bool("Advanced settings", "Adjust factor-selection, fallback, retry, and data-quality controls?", False):
        values["recommendation_weighting_method"] = _ask_choice(
            "Output-row weighting method",
            "Practical output weighting when all gates pass; backtests remain comparable capped top-N portfolios.",
            values["recommendation_weighting_method"],
            ["equal", "score_size_liquidity"],
        )
        for field, label, description in [
            ("recommendation_score_weight", "Output score weight", "Weight assigned to selected-factor rank score when practical output is enabled."),
            ("recommendation_market_cap_weight", "Output market-cap weight", "Weight assigned to market-cap size evidence when practical output is enabled."),
            ("recommendation_liquidity_weight", "Output liquidity weight", "Weight assigned to ADV liquidity evidence when practical output is enabled."),
            ("recommendation_rank_floor", "Output rank floor", "Minimum rank component used before normalization when practical output is enabled."),
        ]:
            values[field] = _ask_value(label, description, values[field], float, lambda value: value >= 0, "enter a non-negative number")
        values["disable_recommendation_market_cap_lookup"] = _ask_bool(
            "Disable market-cap lookup",
            "Skip best-effort yfinance fast_info market-cap enrichment for recommendation weights.",
            values["disable_recommendation_market_cap_lookup"],
        )
        values["price_chunk_size"] = _ask_value("Price chunk size", "Symbols per yfinance batch.", values["price_chunk_size"], int, lambda value: value >= 1, "enter an integer >= 1")
        values["stooq_fallback_limit"] = _ask_optional("Stooq fallback limit", "Missing symbols to retry via Stooq; 0 disables; blank retries all.", values["stooq_fallback_limit"], int, lambda value: value >= 0, "enter an integer >= 0 or blank/none")
        values["finance_datareader_fallback_limit"] = _ask_optional("FinanceDataReader fallback limit", "Still-missing symbols to retry via optional FinanceDataReader; 0 disables; blank retries all.", values["finance_datareader_fallback_limit"], int, lambda value: value >= 0, "enter an integer >= 0 or blank/none")
        values["retry_count"] = _ask_value("Retry count", "Network retry attempts for public data providers.", values["retry_count"], int, lambda value: value >= 0, "enter an integer >= 0")
        values["retry_backoff_seconds"] = _ask_value("Retry backoff seconds", "Pause between provider retries.", values["retry_backoff_seconds"], float, lambda value: value >= 0, "enter a non-negative number")
        values["cost_stress_high_bps"] = _ask_value("High cost stress bps", "Flat bps cost scenario for stressed metrics.", values["cost_stress_high_bps"], float, lambda value: value >= 0, "enter a non-negative number")
        values["sec_user_agent"] = _ask_optional("SEC user agent", "Optional SEC EDGAR contact string for public universe refresh.", values["sec_user_agent"], str, lambda value: bool(value.strip()), "enter a non-empty string or blank/none")
        values["min_avg_volume"] = _ask_value("Minimum 63-day average share volume", "Optional share-volume floor; 0 disables.", values["min_avg_volume"], float, lambda value: value >= 0, "enter a non-negative number")
        values["min_liquidity_observations"] = _ask_value("Minimum liquidity observations", "Required count in price/volume/dollar-volume liquidity window.", values["min_liquidity_observations"], int, lambda value: value >= 1, "enter an integer >= 1")
        values["data_quality_lookback_days"] = _ask_value("Data-quality lookback days", "Recent trading-day lookback for per-symbol data-quality diagnostics.", values["data_quality_lookback_days"], int, lambda value: value >= 1, "enter an integer >= 1")
        values["max_price_missing_ratio"] = _ask_value("Max price missing ratio", "Hard recent missing-price threshold.", values["max_price_missing_ratio"], float, lambda value: 0 <= value <= 1, "enter a decimal in [0, 1]")
        values["max_volume_missing_ratio"] = _ask_value("Max volume missing ratio", "Hard recent missing-volume threshold.", values["max_volume_missing_ratio"], float, lambda value: 0 <= value <= 1, "enter a decimal in [0, 1]")
        values["max_extreme_daily_return"] = _ask_value("Max extreme daily return", "Absolute adjusted daily-return anomaly threshold.", values["max_extreme_daily_return"], float, lambda value: value > 0, "enter a positive number")
        values["selected_factor"] = _ask_optional("Selected factor override", "Optional frozen factor name; blank lets validation select a research-only factor.", values["selected_factor"], str, lambda value: bool(value.strip()), "enter a factor name or blank/none")
        values["factor_selection_mode"] = _ask_choice(
            "Factor selection mode",
            (
                "research_validation and in-run walk-forward stay research-only; only an explicit "
                "predeclared/frozen selected factor can enable practical rows when every tradability gate passes."
            ),
            values["factor_selection_mode"],
            ["research_validation", "predeclared", "walk_forward"],
        )
        values["selection_window"] = _ask_value("Selection window label", "Audit label for factor selection policy/window.", values["selection_window"], str, lambda value: bool(value.strip()), "enter a non-empty label")
        values["frozen_policy_path"] = _ask_optional("Frozen policy path", "Optional path to a frozen/predeclared factor policy artifact.", values["frozen_policy_path"], str, lambda value: bool(value.strip()), "enter a path or blank/none")
        values["point_in_time_universe_provenance"] = _ask_optional("Point-in-time universe provenance", "Optional structured PIT universe evidence string.", values["point_in_time_universe_provenance"], str, lambda value: bool(value.strip()), "enter provenance or blank/none")
        values["approved_tradable_universe"] = _ask_bool("Approved tradable universe", "Attest that a user-supplied small universe is approved for this run.", values["approved_tradable_universe"])
        values["min_tradable_universe_size"] = _ask_value("Minimum tradable universe size", "Minimum broad universe size unless user approval/provenance is supplied.", values["min_tradable_universe_size"], int, lambda value: value >= 1, "enter an integer >= 1")

    return argparse.Namespace(**values)


def _print_config_review(config: RunConfig) -> None:
    print("\nRun configuration review")
    rows = [
        ("mode", "offline_sample" if config.offline_sample else "live"),
        ("start_date", config.start_date),
        ("end_date", config.end_date or "today/default"),
        ("top_n", config.top_n),
        ("max_weight", config.max_weight),
        ("output_dir", config.output_dir),
        ("report_dir", config.report_dir),
        ("universe_size", len(config.universe)),
        ("universe_profile", config.universe_profile),
        ("max_price_symbols", config.max_price_symbols or "none"),
        ("target_aum", config.target_aum or "none"),
        ("max_adv_participation", config.max_adv_participation or "none"),
    ]
    for key, value in rows:
        print(f"  {key}: {value}")


def run_wizard_command(args: argparse.Namespace) -> dict[str, object]:
    wizard_args = _wizard_namespace()
    config = config_from_args(wizard_args)
    config.validate()
    _print_config_review(config)
    if not args.no_confirm and not _ask_bool("Run analysis now", "Execute backtests, factor calculations, and report generation with this configuration?", True):
        raise WizardAbort("interactive wizard cancelled before execution")
    return execute_config(config, emit_json=False)


def dashboard_command(args: argparse.Namespace) -> dict[str, str]:
    paths = write_dashboard_site(args.run_results, args.site_dir, title=args.title, history_limit=args.history_limit)
    if args.json:
        print(json.dumps(paths, indent=2, ensure_ascii=False))
    else:
        print("Dashboard site generated:")
        for key, value in paths.items():
            print(f"  {key}: {value}")
    return paths


def scheduled_dashboard_command(args: argparse.Namespace) -> dict[str, str]:
    config_path = Path(args.config)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"dashboard config not found: {config_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("dashboard config must be a JSON object")
    run_args = payload.get("run_args", [])
    if not isinstance(run_args, list) or not all(isinstance(item, str) for item in run_args):
        raise ValueError("dashboard config field 'run_args' must be a list of strings")
    tokens = run_args if run_args[:1] == ["run"] else ["run", *run_args]
    run_namespace = build_parser().parse_args(tokens)
    if args.json:
        with contextlib.redirect_stdout(io.StringIO()):
            summary = run_command(run_namespace)
    else:
        summary = run_command(run_namespace)
    outputs = summary.get("outputs", {})
    if not isinstance(outputs, dict) or not outputs.get("json"):
        raise ValueError("scheduled analysis did not produce a JSON output path")
    site_dir = args.site_dir or payload.get("site_dir") or "docs"
    title = args.title or payload.get("title") or DEFAULT_SITE_TITLE
    try:
        history_limit = args.history_limit if args.history_limit is not None else int(payload.get("history_limit", 60))
    except (TypeError, ValueError) as exc:
        raise ValueError("dashboard config field 'history_limit' must be an integer") from exc
    if history_limit < 1:
        raise ValueError("history_limit must be at least 1")
    paths = write_dashboard_site([str(outputs["json"])], site_dir, title=str(title), history_limit=history_limit)
    if args.json:
        print(json.dumps(paths, indent=2, ensure_ascii=False))
    else:
        print("Scheduled dashboard updated:")
        for key, value in paths.items():
            print(f"  {key}: {value}")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            run_command(args)
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
        return 0
    if args.command in {"wizard", "run-wizard", "interactive"}:
        try:
            run_wizard_command(args)
        except WizardAbort as exc:
            parser.exit(1, f"error: {exc}\n")
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
        return 0
    if args.command == "dashboard":
        try:
            dashboard_command(args)
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
        return 0
    if args.command == "scheduled-dashboard":
        try:
            scheduled_dashboard_command(args)
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
