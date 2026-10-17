"""add-telemetry-heavy-path-spans, task 6.1: ``docs/OBSERVABILITY.md`` 4.3 and 4.4.

Spec: observability (delta). The unit's final check: sections 4.3 ("Spans to emit") and
4.4 ("Metrics to emit") still describe only the pre-unit instrumentation. This module pins
the new spans and metrics the delta adds, and fails until the green step of task 6.1 updates
the document.

The behavioural half of every span and metric is pinned by the tagged tests of tasks
1.1-5.4; this module pins the documentation half only, so it reads the two sections and
asserts the new names are listed. The criteria tagged here are the requirements whose span
or metric the section must list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

OBSERVABILITY_DOC = Path(__file__).resolve().parents[3] / "docs" / "OBSERVABILITY.md"

_NEW_SPAN_NAMES = (
    "mintmory.search.fts",
    "mintmory.search.substring",
    "mintmory.search.vector",
    "mintmory.search.fusion",
    "mintmory.cli.",
    "mintmory.index_tree.scan",
    "mintmory.index_tree.prune",
    "mintmory.index_tree.cochange",
    "mintmory.convert",
    "mintmory.vision.caption",
)

_NEW_METRIC_MARKERS = (
    "mintmory.search.latency_ms",
    "substring",
    "fusion",
    "mintmory.embed.latency_ms",
    "mintmory.memories.added",
)


def _section(start_heading: str, end_heading: str) -> str:
    """The body of ``start_heading`` up to (not including) ``end_heading``."""
    text = OBSERVABILITY_DOC.read_text(encoding="utf-8")
    start = text.find(start_heading)
    assert start != -1, f"no {start_heading!r} heading in {OBSERVABILITY_DOC}"
    rest = text[start:]
    end = rest.find(end_heading, len(start_heading))
    assert end != -1, f"no {end_heading!r} heading after {start_heading!r}"
    return rest[:end]


@pytest.mark.l4(
    "C-844f12f2",
    "C-f4b27f0d",
    "C-43d72c8b",
    "C-c91ee0e7",
    "C-c986421b",
    "C-20646f63",
    "C-53f9b64c",
    "C-755ec9f3",
    "C-e9540797",
    "C-ebe047e9",
    "C-64a88ce0",
    "C-3ce5b739",
    "C-a83f338b",
    "C-55bbc2f5",
    "C-193aef3b",
    "C-711e3d68",
    "C-28481766",
    "C-395d5e72",
    "C-72a88eb9",
)
def test_spans_section_lists_the_new_spans() -> None:
    """4.3 lists the search phases, CLI roots, index-tree phases, conversion and caption spans."""
    section = _section("### 4.3", "### 4.4")
    missing = [name for name in _NEW_SPAN_NAMES if name not in section]
    assert not missing, f"4.3 Spans to emit is missing {missing}"


@pytest.mark.l4(
    "C-f4b27f0d",
    "C-43d72c8b",
    "C-0d312d3f",
    "C-53f9b64c",
    "C-20646f63",
    "C-910cf3ca",
    "C-3ce5b739",
)
def test_metrics_section_lists_the_new_metrics() -> None:
    """4.4 lists the substring/fusion search phases and the embed and memories metrics."""
    section = _section("### 4.4", "### 4.5")
    missing = [marker for marker in _NEW_METRIC_MARKERS if marker not in section]
    assert not missing, f"4.4 Metrics to emit is missing {missing}"
