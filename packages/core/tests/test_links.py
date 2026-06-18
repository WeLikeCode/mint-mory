"""Unit tests for ConceptLink storage: add_link idempotency and get_links."""

from __future__ import annotations

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import ConceptLink, ConceptLinkType, LinkSource


@pytest.fixture()
def store() -> StorageAdapter:
    s = StorageAdapter(":memory:")
    s.initialise()
    return s


def _mem(store: StorageAdapter, content: str) -> str:
    return store.add_memory(content=content, category="fact").id


def test_add_link_returns_link(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    link = ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.USES)
    returned = store.add_link(link)
    assert returned.id == link.id
    links = store.get_links(a)
    assert len(links) == 1
    assert links[0].link_type == ConceptLinkType.USES


def test_add_link_idempotent_on_unique_triplet(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    store.add_link(
        ConceptLink(
            source_memory_id=a,
            target_memory_id=b,
            link_type=ConceptLinkType.RELATES_TO,
            source=LinkSource.DREAMING,
        )
    )
    # Same triplet, different id — INSERT OR IGNORE must not create a duplicate.
    store.add_link(
        ConceptLink(
            source_memory_id=a,
            target_memory_id=b,
            link_type=ConceptLinkType.RELATES_TO,
            source=LinkSource.USER,
        )
    )
    links = store.get_links(a)
    assert len(links) == 1


def test_add_link_distinct_types_coexist(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.RELATES_TO)
    )
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.USES)
    )
    links = store.get_links(a)
    assert {link.link_type for link in links} == {
        ConceptLinkType.RELATES_TO,
        ConceptLinkType.USES,
    }


def test_get_links_both_directions(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    c = _mem(store, "gamma")
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.USES)
    )
    store.add_link(
        ConceptLink(source_memory_id=c, target_memory_id=a, link_type=ConceptLinkType.DEPENDS_ON)
    )
    # a is source of one, target of the other -> both returned.
    links = store.get_links(a)
    assert len(links) == 2


def test_get_links_filtered_by_type(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    c = _mem(store, "gamma")
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=b, link_type=ConceptLinkType.USES)
    )
    store.add_link(
        ConceptLink(source_memory_id=a, target_memory_id=c, link_type=ConceptLinkType.RELATES_TO)
    )
    uses = store.get_links(a, link_type=ConceptLinkType.USES)
    assert len(uses) == 1
    assert uses[0].target_memory_id == b


def test_link_metadata_round_trip(store: StorageAdapter) -> None:
    a = _mem(store, "alpha")
    b = _mem(store, "beta")
    store.add_link(
        ConceptLink(
            source_memory_id=a,
            target_memory_id=b,
            link_type=ConceptLinkType.SIMILAR_TO,
            entity="shared-entity",
            strength=0.77,
            confidence=0.66,
            source=LinkSource.INFERENCE,
            verified=True,
        )
    )
    link = store.get_links(a)[0]
    assert link.entity == "shared-entity"
    assert link.strength == pytest.approx(0.77)
    assert link.confidence == pytest.approx(0.66)
    assert link.source == LinkSource.INFERENCE
    assert link.verified is True
