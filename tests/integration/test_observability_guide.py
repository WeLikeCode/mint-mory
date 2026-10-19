"""Tests for the observability guide (task 4.1).

Covers the ``Observability guide`` scenarios ``Guide names every variable`` and
``Guide has its parts and links``: section 4 of ``docs/OBSERVABILITY.md`` names
every environment variable MintMory reads, keeps the parts 2 and 3 headings and
adds the guide's own headings, shows the local stack command and the Prometheus
phase query, and ``README.md`` links to the guide and the stack README (the
stack README itself is covered by ``test_observability_stack_readme.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "OBSERVABILITY.md"
README = ROOT / "README.md"

UP_COMMAND = "docker compose -f deploy/observability/compose.yaml up -d"

VARIABLES = (
    "MINTMORY_OTEL_ENABLED",
    "MINTMORY_OTEL_EXPORTER",
    "MINTMORY_OTEL_EXPORT_TIMEOUT_S",
    "MINTMORY_OTEL_SERVICE_NAME",
    "OTEL_SDK_DISABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_TIMEOUT",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_TRACES_SAMPLER",
    "OTEL_TRACES_SAMPLER_ARG",
    "OTEL_PROPAGATORS",
    "OTEL_PYTHON_EXCLUDED_URLS",
)

GUIDE_HEADINGS = (
    "Modes",
    "Variables",
    "Local stack",
    "Finding a slow phase",
    "Production",
)

PART_HEADINGS = (
    "4.3 Spans to emit",
    "4.4 Metrics to emit",
    "Distributed tracing",
)


def _section_4() -> str:
    """The text of ``docs/OBSERVABILITY.md`` from ``## 4.`` up to ``## 5.``."""
    assert GUIDE.is_file(), f"{GUIDE} must exist"
    text = GUIDE.read_text()
    match = re.search(r"^## 4\..*?(?=^## 5\.)", text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"{GUIDE} must have a section '## 4.' ending at '## 5.'"
    return match.group(0)


@pytest.mark.l4("C-3a8ae0df")
def test_guide_names_every_variable() -> None:
    section = _section_4()
    missing = [name for name in VARIABLES if name not in section]
    assert not missing, f"section 4 does not name: {', '.join(missing)}"


@pytest.mark.l4("C-6509c282")
def test_guide_has_its_own_and_the_parts_headings() -> None:
    section = _section_4()
    missing = [name for name in GUIDE_HEADINGS + PART_HEADINGS if name not in section]
    assert not missing, f"section 4 is missing headings: {', '.join(missing)}"


@pytest.mark.l4("C-6509c282")
def test_guide_has_the_local_stack_command_and_phase_query() -> None:
    section = _section_4()
    assert UP_COMMAND in section, f"section 4 must show {UP_COMMAND!r}"
    assert "mintmory_search_latency_ms_bucket" in section


@pytest.mark.l4("C-6509c282")
def test_readme_links_to_the_guide_and_the_stack_readme() -> None:
    assert README.is_file(), f"{README} must exist"
    text = README.read_text()
    assert "docs/OBSERVABILITY.md" in text, "README.md must link to the guide"
    assert "deploy/observability/README.md" in text, "README.md must link to the stack README"
