from __future__ import annotations

import json
from pathlib import Path

from momentum_factor_lab.dashboard_monotonic import (
    decide_monotonic_dashboard,
    load_dashboard_snapshot,
    main,
)


def _write_dashboard(path: Path, *, data_as_of: str, run_timestamp: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at_utc": run_timestamp,
                "latest_run_index": 0,
                "runs": [
                    {
                        "summary": {
                            "data_as_of": data_as_of,
                            "run_timestamp_utc": run_timestamp,
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_monotonic_guard_allows_equal_or_newer_candidate(tmp_path: Path) -> None:
    baseline = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "baseline.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:00:00Z")
    )
    candidate = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "candidate.json", data_as_of="2026-06-10", run_timestamp="2026-06-11T01:00:00Z")
    )

    decision = decide_monotonic_dashboard(baseline, candidate)

    assert decision.passed
    assert "not older" in decision.reason


def test_monotonic_guard_blocks_older_data_as_of(tmp_path: Path) -> None:
    baseline = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "baseline.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:00:00Z")
    )
    candidate = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "candidate.json", data_as_of="2026-06-09", run_timestamp="2026-06-11T01:00:00Z")
    )

    decision = decide_monotonic_dashboard(baseline, candidate)

    assert not decision.passed
    assert "data_as_of" in decision.reason


def test_monotonic_guard_blocks_older_run_timestamp(tmp_path: Path) -> None:
    baseline = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "baseline.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:00:00Z")
    )
    candidate = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "candidate.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T11:59:00Z")
    )

    decision = decide_monotonic_dashboard(baseline, candidate)

    assert not decision.passed
    assert "run_timestamp" in decision.reason


def test_monotonic_guard_normalizes_naive_timestamps(tmp_path: Path) -> None:
    baseline = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "baseline.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:00:00Z")
    )
    candidate = load_dashboard_snapshot(
        _write_dashboard(tmp_path / "candidate.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:01:00")
    )

    decision = decide_monotonic_dashboard(baseline, candidate)

    assert decision.passed


def test_monotonic_guard_cli_returns_nonzero_on_regression(tmp_path: Path, capsys) -> None:
    baseline = _write_dashboard(tmp_path / "baseline.json", data_as_of="2026-06-10", run_timestamp="2026-06-10T12:00:00Z")
    candidate = _write_dashboard(tmp_path / "candidate.json", data_as_of="2026-06-09", run_timestamp="2026-06-11T01:00:00Z")

    exit_code = main(["--baseline", str(baseline), "--candidate", str(candidate)])

    stdout = capsys.readouterr().out
    assert exit_code == 1
    assert "passed=false" in stdout
    assert "baseline_data_as_of=2026-06-10" in stdout
    assert "candidate_data_as_of=2026-06-09" in stdout
