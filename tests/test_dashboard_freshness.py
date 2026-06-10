from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from momentum_factor_lab.dashboard_freshness import decide_dashboard_freshness, load_dashboard_payload, main


def _dashboard(timestamp: str, *, latest_run_index: int = 0) -> dict[str, object]:
    return {
        "schema_version": 1,
        "latest_run_index": latest_run_index,
        "runs": [{"summary": {"run_timestamp_utc": timestamp}}],
    }


def test_schedule_runs_when_latest_execution_is_before_kst_cutoff() -> None:
    decision = decide_dashboard_freshness(
        _dashboard("2026-06-09T17:10:35+00:00"),
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 17, tzinfo=UTC),
    )

    assert decision.skip is False
    assert decision.latest_run_kst is not None
    assert decision.latest_run_kst.hour == 2


def test_schedule_skips_when_dashboard_already_executed_after_kst_cutoff() -> None:
    decision = decide_dashboard_freshness(
        _dashboard("2026-06-09T23:20:00Z"),
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 47, tzinfo=UTC),
    )

    assert decision.skip is True
    assert "already executed after 08:00 KST" in decision.reason


def test_exact_kst_cutoff_counts_as_already_executed() -> None:
    decision = decide_dashboard_freshness(
        _dashboard("2026-06-09T23:00:00Z"),
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 17, tzinfo=UTC),
    )

    assert decision.skip is True


def test_generated_at_is_used_when_run_timestamp_is_missing() -> None:
    decision = decide_dashboard_freshness(
        {
            "schema_version": 1,
            "latest_run_index": 0,
            "runs": [{"generated_at_utc": "2026-06-09T23:20:00Z", "summary": {}}],
        },
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 47, tzinfo=UTC),
    )

    assert decision.skip is True
    assert decision.latest_run_kst is not None
    assert decision.latest_run_kst.hour == 8


def test_manual_dispatch_never_skips_even_after_kst_cutoff() -> None:
    decision = decide_dashboard_freshness(
        _dashboard("2026-06-09T23:20:00+00:00"),
        event_name="workflow_dispatch",
        now=datetime(2026, 6, 9, 23, 47, tzinfo=UTC),
    )

    assert decision.skip is False


def test_invalid_dashboard_payload_fails_open(tmp_path: Path) -> None:
    data_path = tmp_path / "dashboard.json"
    data_path.write_text("{not json", encoding="utf-8")

    decision = decide_dashboard_freshness(
        load_dashboard_payload(data_path),
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 47, tzinfo=UTC),
    )

    assert decision.skip is False
    assert decision.latest_run_kst is None


def test_invalid_latest_index_fails_open() -> None:
    decision = decide_dashboard_freshness(
        _dashboard("2026-06-09T23:20:00+00:00", latest_run_index=99),
        event_name="schedule",
        now=datetime(2026, 6, 9, 23, 47, tzinfo=UTC),
    )

    assert decision.skip is False


def test_dashboard_freshness_cli_emits_github_outputs(tmp_path: Path, capsys) -> None:
    data_path = tmp_path / "dashboard.json"
    data_path.write_text(
        '{"schema_version":1,"latest_run_index":0,"runs":[{"summary":{"run_timestamp_utc":"2026-06-09T23:20:00Z"}}]}',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--event-name",
            "schedule",
            "--data-path",
            str(data_path),
            "--now-utc",
            "2026-06-09T23:47:00+00:00",
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "skip=true" in stdout
    assert "latest_run_kst=2026-06-10T08:20:00+09:00" in stdout
