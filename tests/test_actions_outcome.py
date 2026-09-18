import os
import subprocess
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("override,expected", [
    ({}, 0),
    ({"UPDATE_RESULT": "failure"}, 1),
    ({"BUILD_OUTCOME": "failure"}, 1),
    ({"REFRESH_STATE": "degraded"}, 1),
    ({"REFRESH_STATE": "failed"}, 1),
    ({"DEPLOY_RESULT": "failure"}, 1),
    ({"DEPLOY_RESULT": "skipped"}, 1),
    ({"REFRESH_SKIPPED": "true", "DEPLOY_RESULT": "skipped", "BUILD_OUTCOME": "skipped"}, 0),
    ({"SHOULD_DEPLOY": "false", "DEPLOY_RESULT": "skipped"}, 0),
])
def test_workflow_never_treats_page_reachability_as_a_successful_refresh(override, expected):
    workflow = Path(".github/workflows/daily-dashboard.yml").read_text()
    final_job = workflow.split("  refresh-result:\n", 1)[1]
    script = textwrap.dedent(final_job.split("        run: |\n", 1)[1])
    environment = {
        **os.environ,
        "UPDATE_RESULT": "success",
        "REFRESH_SKIPPED": "false",
        "BUILD_OUTCOME": "success",
        "REFRESH_STATE": "available",
        "DEPLOY_RESULT": "success",
        "SHOULD_DEPLOY": "true",
        **override,
    }
    result = subprocess.run(["bash", "-e", "-c", script], env=environment, capture_output=True)
    assert result.returncode == expected, result.stdout + result.stderr
