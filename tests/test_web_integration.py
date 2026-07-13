from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script",
    [
        "scripts/test_web_contract.mjs",
        "scripts/test_web_dom_integration.mjs",
        "scripts/test_performance_table_dom.mjs",
        "scripts/test_chart_palette_dom.mjs",
        "scripts/test_original_design_contract.mjs",
        "scripts/test_static_web_loader_contract.mjs",
        "scripts/test_web_local_api_dom_integration.mjs",
    ],
)
def test_node_web_contract_and_dom_integration(script: str) -> None:
    completed = subprocess.run(
        ["node", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout
