"""Tests for the Helm telemetry settings (task 3.1).

Covers the ``Helm telemetry settings`` requirement: the ConfigMap template's
sampler guards and its disabled branch, the ``otel`` keys in ``values.yaml``, and
their declaration in ``values.schema.json``. The ``helm template`` checks run only
where ``helm`` exists (the gates have none).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "mintmory"
CONFIGMAP = CHART / "templates" / "configmap.yaml"
VALUES = CHART / "values.yaml"
SCHEMA = CHART / "values.schema.json"

SAMPLER_KEYS = ("sampler", "samplerArg", "resourceAttributes")
SAMPLER_VARS = {
    "sampler": "OTEL_TRACES_SAMPLER",
    "samplerArg": "OTEL_TRACES_SAMPLER_ARG",
    "resourceAttributes": "OTEL_RESOURCE_ATTRIBUTES",
}

_IF = re.compile(r"\{\{-?\s*if\b")
_ELSE = re.compile(r"\{\{-?\s*else\b")
_END = re.compile(r"\{\{-?\s*end\b")


def _otel_branches(text: str) -> tuple[list[str], list[str]]:
    """The then/else lines of the top-level ``if .Values.otel.enabled`` block."""
    lines = text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if ".Values.otel.enabled" in line and _IF.search(line)
        ),
        None,
    )
    assert start is not None, "configmap must gate telemetry on `.Values.otel.enabled`"
    then: list[str] = []
    otherwise: list[str] = []
    branch = then
    depth = 0
    for line in lines[start:]:
        if _IF.search(line):
            depth += 1
            if depth == 1:
                continue
        if _ELSE.search(line) and depth == 1:
            branch = otherwise
            continue
        if _END.search(line):
            depth -= 1
            if depth == 0:
                break
            continue
        if depth >= 1:
            branch.append(line)
    return then, otherwise


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


@pytest.mark.l4("C-ed7d7932")
def test_configmap_guards_sampler_variables_on_their_otel_values() -> None:
    then, _ = _otel_branches(CONFIGMAP.read_text())
    body = "\n".join(then)
    for key, variable in SAMPLER_VARS.items():
        assert re.search(rf"if\s+\.Values\.otel\.{key}\s", body), (
            f"the template must guard {variable} with an `if .Values.otel.{key}`"
        )
        assert re.search(rf"(?<!\w){variable}(?!\w)", body), (
            f"the template must render {variable} inside the otel branch"
        )


@pytest.mark.l4("C-ed7d7932")
def test_values_yaml_declares_empty_sampler_settings() -> None:
    otel = yaml.safe_load(VALUES.read_text())["otel"]
    assert otel.get("enabled") is False
    for key in SAMPLER_KEYS:
        assert otel.get(key) == ""


@pytest.mark.l4("C-ed7d7932")
def test_schema_declares_sampler_settings_as_strings() -> None:
    otel = json.loads(SCHEMA.read_text())["properties"]["otel"]
    properties = otel["properties"]
    for key in SAMPLER_KEYS:
        assert properties.get(key, {}).get("type") == "string"
    assert otel["additionalProperties"] is False


@pytest.mark.l4("C-c7f1a358")
def test_configmap_renders_disabled_in_the_else_branch() -> None:
    _, otherwise = _otel_branches(CONFIGMAP.read_text())
    assert 'MINTMORY_OTEL_ENABLED: "false"' in "\n".join(otherwise)


@pytest.mark.l4("C-7836148e")
def test_helm_template_defaults_disable_telemetry() -> None:
    output = _helm_template()
    assert 'MINTMORY_OTEL_ENABLED: "false"' in output
    assert "OTEL_TRACES_SAMPLER" not in output


@pytest.mark.l4("C-7836148e")
def test_helm_template_renders_sampler_values() -> None:
    output = _helm_template(
        "--set",
        "otel.enabled=true",
        "--set-string",
        "otel.sampler=parentbased_traceidratio,otel.samplerArg=0.1",
    )
    assert 'OTEL_TRACES_SAMPLER: "parentbased_traceidratio"' in output
    assert 'OTEL_TRACES_SAMPLER_ARG: "0.1"' in output
    assert "OTEL_RESOURCE_ATTRIBUTES" not in output
