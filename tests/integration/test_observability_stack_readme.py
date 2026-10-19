"""Tests for the local observability stack README (task 1.6).

Covers the ``Observability guide`` scenario ``Guide has its parts and links`` for
``deploy/observability/README.md``: the stack README gives the quick start
command the criterion names, and documents the Jaeger and Prometheus viewers,
the Prometheus phase query, the optional ``api`` profile and how to stop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "deploy" / "observability"
README = STACK / "README.md"

UP_COMMAND = "docker compose -f deploy/observability/compose.yaml up -d"


@pytest.mark.l4("C-6509c282")
def test_stack_readme_gives_the_quick_start_command() -> None:
    assert README.is_file(), f"{README} must exist"
    text = README.read_text()
    assert UP_COMMAND in text, f"{README} must document {UP_COMMAND!r}"


@pytest.mark.l4("C-6509c282")
def test_stack_readme_documents_the_viewers_and_api_profile() -> None:
    assert README.is_file(), f"{README} must exist"
    text = README.read_text()
    assert "http://localhost:16686" in text, "the README must point at the Jaeger UI"
    assert "http://localhost:9090" in text, "the README must point at the Prometheus UI"
    assert "mintmory_search_latency_ms_bucket" in text, "the README must show the phase query"
    assert "--profile api up -d --build" in text, "the README must show the api profile"
    assert "down -v" in text, "the README must show how to stop and drop the volume"
