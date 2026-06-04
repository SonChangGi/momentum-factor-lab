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
    mode.add_argument("--live", action="store_true", help="Try live yfinance free/public data")
    run.add_argument("--start-date", default="2016-01-01")
    run.add_argument("--end-date", default=None)
    run.add_argument("--output-dir", default="outputs/sample")
    run.add_argument("--report-dir", default="reports/sample")
    run.add_argument("--universe", default=None, help="Comma-separated symbols")
    run.add_argument("--top-n", type=int, default=15)
    run.add_argument("--max-weight", type=float, default=0.10)
    run.add_argument("--json", action="store_true", help="Emit machine-readable summary")
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    config = RunConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=Path(args.output_dir),
        report_dir=Path(args.report_dir),
        offline_sample=not args.live,
        universe=normalize_symbols(args.universe),
        top_n=args.top_n,
        max_weight=args.max_weight,
    )
    result = write_reports(run_analysis(config))
    summary = {
        "selected_factor": result.selected_factor,
        "recommendation_status": result.metadata["recommendation_status"],
        "current_recommendations_available": result.metadata["current_recommendations_available"],
        "data_as_of": result.metadata["data_as_of"],
        "provider": result.metadata["provider"],
        "outputs": result.output_paths,
        "top_recommendations": result.recommendations.head(result.config.top_n).to_dict(orient="records"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"Selected factor: {summary['selected_factor']}")
        print(f"Recommendation status: {summary['recommendation_status']}")
        print(f"Data as of: {summary['data_as_of']} via {summary['provider']}")
        print("Outputs:")
        for key, value in result.output_paths.items():
            print(f"  {key}: {value}")
        print("Top recommendations:")
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
