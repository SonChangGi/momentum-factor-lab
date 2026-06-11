from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DashboardSnapshot:
    path: str
    data_as_of: date | None
    run_timestamp: datetime | None
    generated_at_utc: datetime | None


@dataclass(frozen=True)
class MonotonicDashboardDecision:
    passed: bool
    baseline: DashboardSnapshot
    candidate: DashboardSnapshot
    reason: str

    def as_github_outputs(self) -> dict[str, str]:
        return {
            "passed": "true" if self.passed else "false",
            "reason": self.reason,
            "baseline_data_as_of": self.baseline.data_as_of.isoformat() if self.baseline.data_as_of else "none",
            "candidate_data_as_of": self.candidate.data_as_of.isoformat() if self.candidate.data_as_of else "none",
            "baseline_run_timestamp": self.baseline.run_timestamp.isoformat() if self.baseline.run_timestamp else "none",
            "candidate_run_timestamp": self.candidate.run_timestamp.isoformat() if self.candidate.run_timestamp else "none",
        }


def load_dashboard_snapshot(path: str | Path) -> DashboardSnapshot:
    payload = _load_json(path)
    latest = _latest_run(payload)
    summary = latest.get("summary", {}) if isinstance(latest.get("summary"), dict) else {}
    return DashboardSnapshot(
        path=str(path),
        data_as_of=_parse_date(summary.get("data_as_of") or latest.get("data_as_of")),
        run_timestamp=_parse_datetime(summary.get("run_timestamp_utc") or latest.get("generated_at_utc")),
        generated_at_utc=_parse_datetime(payload.get("generated_at_utc")),
    )


def decide_monotonic_dashboard(
    baseline: DashboardSnapshot,
    candidate: DashboardSnapshot,
) -> MonotonicDashboardDecision:
    if baseline.data_as_of and candidate.data_as_of and candidate.data_as_of < baseline.data_as_of:
        return MonotonicDashboardDecision(
            passed=False,
            baseline=baseline,
            candidate=candidate,
            reason="candidate dashboard data_as_of is older than remote baseline",
        )
    if baseline.run_timestamp and candidate.run_timestamp and candidate.run_timestamp < baseline.run_timestamp:
        return MonotonicDashboardDecision(
            passed=False,
            baseline=baseline,
            candidate=candidate,
            reason="candidate dashboard run_timestamp is older than remote baseline",
        )
    if baseline.data_as_of and not candidate.data_as_of:
        return MonotonicDashboardDecision(
            passed=False,
            baseline=baseline,
            candidate=candidate,
            reason="candidate dashboard is missing data_as_of while remote baseline has one",
        )
    if baseline.run_timestamp and not candidate.run_timestamp:
        return MonotonicDashboardDecision(
            passed=False,
            baseline=baseline,
            candidate=candidate,
            reason="candidate dashboard is missing run_timestamp while remote baseline has one",
        )
    return MonotonicDashboardDecision(
        passed=True,
        baseline=baseline,
        candidate=candidate,
        reason="candidate dashboard is not older than remote baseline",
    )


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_run(payload: dict[str, Any]) -> dict[str, Any]:
    runs = payload.get("runs")
    if isinstance(runs, list) and runs:
        latest_index = payload.get("latest_run_index", len(runs) - 1)
        try:
            latest = runs[int(latest_index)]
        except (IndexError, TypeError, ValueError):
            latest = runs[-1]
        return latest if isinstance(latest, dict) else {}
    return payload


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prevent generated dashboard data from moving backwards.")
    parser.add_argument("--baseline", required=True, help="Remote/current dashboard JSON baseline")
    parser.add_argument("--candidate", required=True, help="Generated dashboard JSON candidate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    decision = decide_monotonic_dashboard(
        load_dashboard_snapshot(args.baseline),
        load_dashboard_snapshot(args.candidate),
    )
    for key, value in decision.as_github_outputs().items():
        print(f"{key}={value}")
    return 0 if decision.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
