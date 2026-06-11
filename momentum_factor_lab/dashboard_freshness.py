from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
DEFAULT_CUTOFF_HOUR_KST = 8


@dataclass(frozen=True)
class DashboardFreshnessDecision:
    """Decision used by scheduled GitHub Actions fallback runs."""

    skip: bool
    event_name: str
    latest_run_kst: datetime | None
    latest_data_as_of: date | None
    target_data_as_of: date
    cutoff_kst: datetime
    reason: str

    def as_github_outputs(self) -> dict[str, str]:
        return {
            "skip": "true" if self.skip else "false",
            "event_name": self.event_name,
            "latest_run_kst": self.latest_run_kst.isoformat() if self.latest_run_kst else "none",
            "latest_data_as_of": self.latest_data_as_of.isoformat() if self.latest_data_as_of else "none",
            "target_data_as_of": self.target_data_as_of.isoformat(),
            "cutoff_kst": self.cutoff_kst.isoformat(),
            "reason": self.reason,
        }


def decide_dashboard_freshness(
    dashboard: dict[str, Any],
    *,
    event_name: str,
    now: datetime | None = None,
    cutoff_hour_kst: int = DEFAULT_CUTOFF_HOUR_KST,
) -> DashboardFreshnessDecision:
    """Return whether a scheduled fallback run should skip duplicate work.

    Manual dispatches never skip. Scheduled retries skip only when the dashboard
    both executed after the Korean 08:00 cutoff and already covers the expected
    latest U.S. close date. This prevents an early provider-lagged run from
    suppressing later retry windows for the same Korean calendar day.
    """

    now_kst = _to_kst(now) if now else datetime.now(KST)
    cutoff_kst = datetime.combine(now_kst.date(), time(hour=cutoff_hour_kst), tzinfo=KST)
    latest_run_kst = latest_dashboard_run_kst(dashboard)
    latest_data_as_of = latest_dashboard_data_as_of(dashboard)
    target_data_as_of = expected_recent_us_close_date(now_kst)
    already_executed_after_cutoff = latest_run_kst is not None and latest_run_kst >= cutoff_kst
    data_covers_target = latest_data_as_of is not None and latest_data_as_of >= target_data_as_of
    skip = event_name == "schedule" and already_executed_after_cutoff and data_covers_target
    if skip:
        reason = "scheduled fallback skipped because dashboard already executed after 08:00 KST with target data_as_of"
    elif event_name == "schedule" and already_executed_after_cutoff and not data_covers_target:
        reason = "dashboard retry required because latest execution did not reach target data_as_of"
    else:
        reason = "dashboard execution required"
    return DashboardFreshnessDecision(
        skip=skip,
        event_name=event_name,
        latest_run_kst=latest_run_kst,
        latest_data_as_of=latest_data_as_of,
        target_data_as_of=target_data_as_of,
        cutoff_kst=cutoff_kst,
        reason=reason,
    )


def latest_dashboard_data_as_of(dashboard: dict[str, Any]) -> date | None:
    """Extract the latest run market-data date from a combined dashboard payload."""

    latest = _latest_dashboard_run(dashboard)
    if latest is None:
        return None
    summary = latest.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return _parse_date(summary.get("data_as_of") or latest.get("data_as_of"))


def expected_recent_us_close_date(now_kst: datetime) -> date:
    """Return the most recent likely U.S. daily close date for a KST morning run.

    The automation uses free end-of-day providers, so this intentionally stays
    conservative and dependency-free before package installation. It handles
    weekends; U.S. market holidays may cause harmless extra retry attempts until
    the dashboard data date catches up on the next trading day.
    """

    candidate = now_kst.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _latest_dashboard_run(dashboard: dict[str, Any]) -> dict[str, Any] | None:
    runs = dashboard.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    latest_index = dashboard.get("latest_run_index", len(runs) - 1)
    try:
        latest = runs[int(latest_index)]
    except (IndexError, TypeError, ValueError):
        return None
    return latest if isinstance(latest, dict) else None


def latest_dashboard_run_kst(dashboard: dict[str, Any]) -> datetime | None:
    """Extract the latest run timestamp from a combined dashboard payload."""

    latest = _latest_dashboard_run(dashboard)
    if latest is None:
        return None
    summary = latest.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    raw_timestamp = summary.get("run_timestamp_utc") or latest.get("generated_at_utc")
    return _parse_timestamp_to_kst(raw_timestamp)


def load_dashboard_payload(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_timestamp_to_kst(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _to_kst(parsed)


def _to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(KST)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decide whether a scheduled dashboard fallback should run.")
    parser.add_argument("--event-name", required=True, help="GitHub event name, e.g. schedule or workflow_dispatch")
    parser.add_argument("--data-path", default="docs/data/dashboard.json", help="Dashboard JSON path to inspect")
    parser.add_argument("--now-utc", default=None, help="Optional ISO timestamp for deterministic tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    now = _parse_timestamp_to_kst(args.now_utc) if args.now_utc else None
    decision = decide_dashboard_freshness(
        load_dashboard_payload(args.data_path),
        event_name=args.event_name,
        now=now,
    )
    for key, value in decision.as_github_outputs().items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
