"""add-telemetry-boundary-tracing, task 5.1: ``docs/OBSERVABILITY.md`` section 4.

Spec: observability (delta). The unit's final check adds a "Distributed tracing"
part to section 4 stating what continues a trace and what MintMory sends. The
behavioural half of every requirement is pinned by the tagged tests of tasks
1.1-4.3; this module pins the documentation half only, so it reads section 4 and
asserts the new text names the inbound context (W3C ``traceparent``, MCP
``_meta``) and the outbound headers (``traceparent``/``tracestate``, never
``baggage``). It fails until the green step of task 5.1 updates the document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

OBSERVABILITY_DOC = Path(__file__).resolve().parents[3] / "docs" / "OBSERVABILITY.md"

_DISTRIBUTED_TRACING = "Distributed tracing"


def _section_4() -> str:
    """The body of ``## 4. OpenTelemetry plan (R5)`` up to the ``## 5.`` heading."""
    text = OBSERVABILITY_DOC.read_text(encoding="utf-8")
    start = text.find("## 4.")
    assert start != -1, f"no '## 4.' heading in {OBSERVABILITY_DOC}"
    rest = text[start:]
    end = rest.find("## 5.", len("## 4."))
    assert end != -1, f"no '## 5.' heading after '## 4.' in {OBSERVABILITY_DOC}"
    return rest[:end]


@pytest.mark.l4("C-dc87542c", "C-da502b68")
def test_section_4_documents_what_continues_a_trace() -> None:
    """Section 4 names the incoming context the HTTP and MCP boundaries continue."""
    section = _section_4()
    assert _DISTRIBUTED_TRACING in section, "section 4 has no 'Distributed tracing' text"
    missing = [marker for marker in ("traceparent", "W3C", "_meta") if marker not in section]
    assert not missing, f"section 4 Distributed tracing is missing {missing}"


@pytest.mark.l4("C-83e1a4e6", "C-9970c315", "C-d1b2babd", "C-c2076c0f")
def test_section_4_documents_what_mintmory_sends() -> None:
    """Section 4 names the outbound headers: traceparent and tracestate, no baggage."""
    section = _section_4()
    assert _DISTRIBUTED_TRACING in section, "section 4 has no 'Distributed tracing' text"
    markers = ("traceparent", "tracestate", "baggage")
    missing = [marker for marker in markers if marker not in section]
    assert not missing, f"section 4 Distributed tracing is missing {missing}"
