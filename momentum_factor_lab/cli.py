from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import RunConfig
from .report import write_reports
from .universe import normalize_symbols
from .workflow import run_analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Momentum Factor Lab analysis.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run factor comparison and report generation")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--offline-sample", action="store_true", help="Use deterministic offline sample data")
    mode.add_argument("--live", action="store_true", help="Try live yfinance/Stooq free/public data")
    run.add_argument("--start-date", default="2016-01-01")
    run.add_argument("--end-date", default=None)
    run.add_argument("--output-dir", default="outputs/sample")
    run.add_argument("--report-dir", default="reports/sample")
    run.add_argument("--cache-dir", default=".cache/momentum_factor_lab")
    run.add_argument("--universe", default=None, help="Comma-separated symbols; omitted uses packaged 2,000+ universe")
    run.add_argument("--universe-source-mode", choices=["packaged", "refresh"], default="packaged")
    run.add_argument(
        "--universe-profile",
        choices=["large_liquid", "extended_current", "aggressive_stock_only"],
        default="large_liquid",
        help="Candidate-universe profile; refresh/current profiles remain research-only without PIT evidence.",
    )
    run.add_argument("--top-n", type=int, default=20)
    run.add_argument("--max-weight", type=float, default=0.10)
    run.add_argument("--max-price-symbols", type=int, default=None, help="Optional live/smoke cap; reports are marked subset when used")
    run.add_argument("--price-chunk-size", type=int, default=150)
    run.add_argument("--stooq-fallback-limit", type=int, default=0)
    run.add_argument("--retry-count", type=int, default=1)
    run.add_argument("--retry-backoff-seconds", type=float, default=0.5)
    run.add_argument("--cost-stress-high-bps", type=float, default=50.0)
    run.add_argument(
        "--sec-user-agent",
        default=None,
        help="SEC EDGAR User-Agent/contact string; can also be set with MOMENTUM_FACTOR_LAB_SEC_USER_AGENT.",
    )
    run.add_argument("--min-price", type=float, default=5.0)
    run.add_argument("--min-avg-dollar-volume", type=float, default=5_000_000.0)
    run.add_argument("--min-avg-volume", type=float, default=0.0)
    run.add_argument("--min-history-days", type=int, default=252)
    run.add_argument(
        "--min-liquidity-observations",
        type=int,
        default=63,
        help="Minimum non-null price/volume/dollar-volume observations required in the 63-day liquidity window",
    )
    run.add_argument("--target-aum", type=float, default=None, help="Target AUM used only for capacity diagnostics/gating")
    run.add_argument(
        "--max-adv-participation",
        type=float,
        default=None,
        help="Maximum share of 63-day ADV a target position may consume before tradable output is blocked",
    )
    run.add_argument(
        "--selected-factor",
        default=None,
        help="Frozen/predeclared factor required for live tradable recommendations; validation rankings remain audit-only.",
    )
    run.add_argument(
        "--factor-selection-mode",
        choices=["research_validation", "predeclared", "walk_forward"],
        default="research_validation",
        help="How the selected factor is controlled for anti-overfit gating.",
    )
    run.add_argument("--selection-window", default="validation_split_70_30")
    run.add_argument("--frozen-policy-path", default=None)
    run.add_argument(
        "--point-in-time-universe-provenance",
        default=None,
        help="Explicit provenance/attestation for point-in-time universe evidence; current public universes remain research-only without it.",
    )
    run.add_argument(
        "--approved-tradable-universe",
        action="store_true",
        help="Attest that a user-supplied small universe is an approved tradable universe; still requires PIT provenance and capacity gates.",
    )
    run.add_argument("--min-tradable-universe-size", type=int, default=2_000)
    run.add_argument("--json", action="store_true", help="Emit machine-readable summary")
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    config = RunConfig(
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
        max_price_symbols=args.max_price_symbols,
        price_chunk_size=args.price_chunk_size,
        stooq_fallback_limit=args.stooq_fallback_limit,
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
    )
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
        "tradability_blockers": result.metadata.get("tradability_blockers", []),
        "recommendation_capacity_warning": result.metadata.get("recommendation_capacity_warning"),
        "outputs": result.output_paths,
        f"top_{output_key}": result.recommendations.head(result.config.top_n).to_dict(orient="records"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"Selected factor: {summary['selected_factor']}")
        print(f"Output status: {summary['recommendation_status']}")
        print(f"Output type: {summary['recommendation_output']}")
        print(f"Fresh live data available: {summary['fresh_live_data_available']}")
        blockers = summary["tradability_blockers"]
        print(f"Tradability blockers: {', '.join(blockers) if blockers else 'none'}")
        print(f"Liquidity/capacity: {summary['recommendation_capacity_warning']}")
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
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        try:
            run_command(args)
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
