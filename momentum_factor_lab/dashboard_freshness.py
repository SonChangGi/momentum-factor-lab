from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
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
    cutoff_kst: datetime
    reason: str

    def as_github_outputs(self) -> dict[str, str]:
        return {
            "skip": "true" if self.skip else "false",
            "event_name": self.event_name,
            "latest_run_kst": self.latest_run_kst.isoformat() if self.latest_run_kst else "none",
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

    The guard intentionally checks execution freshness, not whether `data_as_of`
    advanced, because US holidays/weekends can legitimately keep the market data
    기준일 unchanged. Manual dispatches never skip.
    """

    now_kst = _to_kst(now) if now else datetime.now(KST)
    cutoff_kst = datetime.combine(now_kst.date(), time(hour=cutoff_hour_kst), tzinfo=KST)
    latest_run_kst = latest_dashboard_run_kst(dashboard)
    already_executed_after_cutoff = latest_run_kst is not None and latest_run_kst >= cutoff_kst
    skip = event_name == "schedule" and already_executed_after_cutoff
    reason = (
        "scheduled fallback skipped because dashboard already executed after 08:00 KST"
        if skip
        else "dashboard execution required"
    )
    return DashboardFreshnessDecision(
        skip=skip,
        event_name=event_name,
        latest_run_kst=latest_run_kst,
        cutoff_kst=cutoff_kst,
        reason=reason,
    )


def latest_dashboard_run_kst(dashboard: dict[str, Any]) -> datetime | None:
    """Extract the latest run timestamp from a combined dashboard payload."""

    runs = dashboard.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    latest_index = dashboard.get("latest_run_index", len(runs) - 1)
    try:
        latest = runs[int(latest_index)]
    except (IndexError, TypeError, ValueError):
        return None
    if not isinstance(latest, dict):
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
