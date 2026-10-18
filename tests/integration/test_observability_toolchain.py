"""Unconditional Helm and Docker command checks for the observability stack.

FB-001 (F-f5fcb85c): three command-backed tests in
``tests/integration/test_helm_telemetry.py`` and
``tests/integration/test_observability_stack.py`` carried
``@pytest.mark.skipif(shutil.which(...) is None, ...)`` markers, which hid the
rendered output from any run that lacks the tool and are refused by the
harness's integrity check. Those files are frozen, so the same checks are
restated here without a skip marker: ``helm`` and ``docker`` are on the gate
runner, so the commands run and their real output is asserted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "mintmory"
COMPOSE = ROOT / "deploy" / "observability" / "compose.yaml"


def _helm_template(*args: str) -> str:
    """``helm template`` output for the chart, failing loudly on a helm error."""
    result = subprocess.run(
        ["helm", "template", "mintmory", str(CHART), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.l4("C-7836148e")
def test_helm_template_renders_disabled_telemetry_without_a_skip() -> None:
    output = _helm_template()
    assert 'MINTMORY_OTEL_ENABLED: "false"' in output
    assert "OTEL_TRACES_SAMPLER" not in output


@pytest.mark.l4("C-7836148e")
def test_helm_template_renders_sampler_values_without_a_skip() -> None:
    output = _helm_template(
        "--set",
        "otel.enabled=true",
        "--set-string",
        "otel.sampler=parentbased_traceidratio,otel.samplerArg=0.1",
    )
    assert 'OTEL_TRACES_SAMPLER: "parentbased_traceidratio"' in output
    assert 'OTEL_TRACES_SAMPLER_ARG: "0.1"' in output
    assert "OTEL_RESOURCE_ATTRIBUTES" not in output


@pytest.mark.l4("C-d797e1ac")
def test_docker_compose_config_accepts_the_stack_without_a_skip() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
