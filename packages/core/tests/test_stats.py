"""Unit tests for StorageAdapter.get_stats and summary storage."""

from __future__ import annotations

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryStats,
    MemorySummary,
)


@pytest.fixture()
def store() -> StorageAdapter:
    s = StorageAdapter(":memory:")
    s.initialise()
    return s


def test_empty_stats(store: StorageAdapter) -> None:
    stats = store.get_stats()
    assert isinstance(stats, MemoryStats)
    assert stats.total_memories == 0
    assert stats.active == 0
    assert stats.stale == 0
    assert stats.archived == 0
    assert stats.concept_links == 0
    assert stats.memory_summaries == 0
    assert stats.avg_usefulness_score == 0.0
    assert stats.avg_staleness_score == 0.0
    assert stats.top_concepts == []


def test_stats_counts(store: StorageAdapter) -> None:
    a = store.add_memory(content="Active fact one", category="fact").id
    store.add_memory(content="Active fact two", category="fact")
    stale = store.add_memory(content="Stale memory item", category="fact", is_stale=True).id
    archived = store.add_memory(content="To archive", category="fact").id
    store.archive_memory(archived)

    stats = store.get_stats()
    assert stats.total_memories == 4
    # active: a, two, stale(is_active default True, not archived) = 3 active non-archived
    assert stats.active == 3
    assert stats.stale == 1
    assert stats.archived == 1
    assert a is not None
    assert stale is not None


def test_stats_link_and_summary_counts(store: StorageAdapter) -> None:
    a = store.add_memory(content="alpha node", category="fact").id
    b = store.add_memory(content="beta node", category="fact").id
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.RELATES_TO)
    )
    store.upsert_summary(
        MemorySummary(concept="alpha", summary_text="summary of alpha", memory_count=1)
    )
    stats = store.get_stats()
    assert stats.concept_links == 1
    assert stats.memory_summaries == 1


def test_stats_avg_scores(store: StorageAdapter) -> None:
    store.add_memory(content="useful one", category="fact", usefulness_score=4.0)
    store.add_memory(content="useful two", category="fact", usefulness_score=6.0)
    stats = store.get_stats()
    assert stats.avg_usefulness_score == pytest.approx(5.0)


def test_stats_top_concepts(store: StorageAdapter) -> None:
    store.add_memory(content="Claude builds things", category="fact")
    store.add_memory(content="Claude is helpful", category="fact")
    store.add_memory(content="MCP protocol details", category="fact")
    stats = store.get_stats()
    concept_map = dict(stats.top_concepts)
    assert concept_map.get("claude", 0) >= 2
    assert "mcp" in concept_map


def test_top_concepts_truncated_to_20(store: StorageAdapter) -> None:
    # 30 distinct capitalised entities -> top_concepts must cap at 20.
    for i in range(30):
        store.add_memory(content=f"Entity{i} appears here", category="fact")
    stats = store.get_stats()
    assert len(stats.top_concepts) <= 20


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------


def test_upsert_summary_insert_then_replace(store: StorageAdapter) -> None:
    first = store.upsert_summary(MemorySummary(concept="topic", summary_text="v1", memory_count=1))
    second = store.upsert_summary(MemorySummary(concept="topic", summary_text="v2", memory_count=5))
    # Same concept -> single row, id stable from the first insert.
    assert second.id == first.id
    fetched = store.get_summary("topic")
    assert fetched is not None
    assert fetched.summary_text == "v2"
    assert fetched.memory_count == 5
    assert len(store.list_summaries()) == 1


def test_get_summary_missing(store: StorageAdapter) -> None:
    assert store.get_summary("nope") is None


def test_list_summaries_sorted(store: StorageAdapter) -> None:
    store.upsert_summary(MemorySummary(concept="zebra", summary_text="z", memory_count=1))
    store.upsert_summary(MemorySummary(concept="apple", summary_text="a", memory_count=1))
    concepts = [s.concept for s in store.list_summaries()]
    assert concepts == ["apple", "zebra"]
