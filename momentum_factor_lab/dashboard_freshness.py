from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
DEFAULT_CUTOFF_HOUR_KST = 6
DEFAULT_CUTOFF_MINUTE_KST = 30


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
            "latest_data_as_of": self.latest_data_as_of.isoformat()
            if self.latest_data_as_of
            else "none",
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
    cutoff_minute_kst: int = DEFAULT_CUTOFF_MINUTE_KST,
) -> DashboardFreshnessDecision:
    """Require snapshot revalidation before any scheduled analysis-cache hit.

    A published date and generation timestamp cannot prove that provider data,
    the universe, factor code, policy code, or selection rules are unchanged.
    Therefore this preflight never skips a scheduled or manual run. The run may
    still finish cheaply after market refresh when its content-addressed result
    identity matches the analysis cache.
    """

    now_kst = _to_kst(now) if now else datetime.now(KST)
    cutoff_kst = datetime.combine(
        now_kst.date(), time(hour=cutoff_hour_kst, minute=cutoff_minute_kst), tzinfo=KST
    )
    latest_run_kst = latest_dashboard_run_kst(dashboard)
    latest_data_as_of = latest_dashboard_data_as_of(dashboard)
    target_data_as_of = expected_recent_us_close_date(now_kst)
    skip = False
    reason = (
        "scheduled snapshot revalidation required before content-addressed cache lookup"
        if event_name == "schedule"
        else "manual dashboard execution required"
    )
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
    """Extract the actual market-data date from schema-v4 or legacy payloads."""

    if dashboard.get("schemaVersion") == 4:
        data = dashboard.get("data")
        return _parse_date(data.get("asOf")) if isinstance(data, dict) else None

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
    """Extract the generation timestamp from schema-v4 or legacy payloads."""

    if dashboard.get("schemaVersion") == 4:
        return _parse_timestamp_to_kst(dashboard.get("generatedAtUtc"))

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
    parser = argparse.ArgumentParser(
        description="Decide whether a scheduled dashboard fallback should run."
    )
    parser.add_argument(
        "--event-name", required=True, help="GitHub event name, e.g. schedule or workflow_dispatch"
    )
    parser.add_argument(
        "--data-path", default="docs/data/dashboard.json", help="Dashboard JSON path to inspect"
    )
    parser.add_argument(
        "--now-utc", default=None, help="Optional ISO timestamp for deterministic tests"
    )
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
