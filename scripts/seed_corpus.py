"""
Load the extracted typed corpus into a MintMory database, run local-LLM dreaming,
and demonstrate the three memory tiers:

  L1 (atomic)      typed MemoryRecords across the 8 categories
  L2 (associative) ConceptLink graph + search-around ("get related elements")
  L3 (synthesized) per-concept MemorySummary records (built by dreaming via Ollama)

plus passive contradiction detection/resolution.

Reads every JSON slice in scripts/corpus_parts/ (produced by the extraction
workflow). Embeddings use the pure-Python default (MINTMORY_EMBED_PROVIDER, default
hashing). The LLM (summaries + contradiction resolution) is opt-in and configured
via MINTMORY_LLM_* (core/llm.py); with provider=none or --no-llm the seed runs
fully offline (L1 + L2 graph only).

Usage:
  MINTMORY_LLM_PROVIDER=ollama uv run python scripts/seed_corpus.py --db /tmp/mintmory_corpus.db
  uv run python scripts/seed_corpus.py --no-llm        # deterministic, no LLM
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from mintmory.core.config import load_settings
from mintmory.core.embedder import embedder_from_settings
from mintmory.core.llm import LLMClient, build_dreaming_engine, check_contradiction
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    SearchAroundSpec,
    SearchRequest,
)

PARTS_DIR = Path(__file__).resolve().parent / "corpus_parts"
VALID_CATEGORIES = {c.value for c in MemoryCategory}
VALID_SOURCES = {s.value for s in MemorySource}


def load_corpus() -> list[dict[str, Any]]:
    """Read + validate every memory object from the corpus_parts/*.json slices."""
    items: list[dict[str, Any]] = []
    files = sorted(PARTS_DIR.glob("*.json"))
    if not files:
        raise SystemExit(
            f"No corpus slices found in {PARTS_DIR}. Run the extraction workflow first."
        )
    for f in files:
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"  ! skipping {f.name}: invalid JSON ({e})")
            continue
        rows = data if isinstance(data, list) else data.get("memories", [])
        kept = 0
        for item in rows:
            cat = str(item.get("category", "")).lower()
            if cat not in VALID_CATEGORIES or not str(item.get("content", "")).strip():
                continue
            item["category"] = cat
            src = str(item.get("source", "document")).lower()
            item["source"] = src if src in VALID_SOURCES else "document"
            items.append(item)
            kept += 1
        print(f"  loaded {kept:3d} records from {f.name}")
    return items


def ingest(store: StorageAdapter, items: list[dict[str, Any]]) -> list[MemoryRecord]:
    """Add every record (entity extraction + embedding happen inside add_memory)."""
    added: list[MemoryRecord] = []
    for item in items:
        fields: dict[str, Any] = {
            "content": item["content"][:10_000],
            "category": item["category"],
            "source": item["source"],
            "metadata": item.get("metadata") or {},
        }
        if item.get("valid_from"):
            fields["valid_from"] = item["valid_from"]
        if item.get("valid_until"):
            fields["valid_until"] = item["valid_until"]
        added.append(store.add_memory(**fields))
    return added


def detect_contradictions(
    client: LLMClient,
    store: StorageAdapter,
    added: list[MemoryRecord],
    items: list[dict[str, Any]],
) -> int:
    """For each flagged candidate, LLM-check against entity-sharing peers; set
    flagged_for_review + contradicts_ids bidirectionally when a conflict is found."""
    flagged = 0
    by_id = {rec.id: rec for rec in added}
    for rec, item in zip(added, items, strict=True):
        if not item.get("contradiction_candidate"):
            continue
        ents = set(rec.entity_ids)
        peers = [(o.id, o.content) for o in added if o.id != rec.id and ents & set(o.entity_ids)][
            :8
        ]
        result = check_contradiction(client, rec.content, peers)
        if not result.has_conflict:
            continue
        conflict_ids = [
            c.existing_memory_id for c in result.conflicts if c.existing_memory_id in by_id
        ]
        if not conflict_ids:
            continue
        store.update_memory(rec.id, flagged_for_review=True, contradicts_ids=conflict_ids)
        for cid in conflict_ids:
            peer = store.get_memory(cid)
            if peer is not None:
                merged = sorted({*peer.contradicts_ids, rec.id})
                store.update_memory(cid, flagged_for_review=True, contradicts_ids=merged)
        flagged += 1
        print(f"  ! contradiction: {rec.content[:60]!r} vs {len(conflict_ids)} memory(ies)")
    return flagged


def demo(store: StorageAdapter, use_llm: bool) -> None:
    stats = store.get_stats()
    print("\n=== L1: typed memory store ===")
    print(
        f"  total={stats.total_memories} active={stats.active} stale={stats.stale} "
        f"archived={stats.archived} | links={stats.concept_links} "
        f"summaries={stats.memory_summaries}"
    )
    print("  top concepts:", ", ".join(f"{c}({n})" for c, n in stats.top_concepts[:10]))

    print("\n=== L2: search-around (related elements via the concept graph) ===")
    for query in ("iOS cancel endpoint bug", "INGHub mobile delivery"):
        resp = store.search(
            SearchRequest(
                query=query,
                limit=5,
                search_around=SearchAroundSpec(depth=2, link_types=[ConceptLinkType.RELATES_TO]),
            )
        )
        print(
            f"\n  query: {query!r}  ->  {resp.total_found} hit(s), "
            f"{len(resp.search_around_ids)} added by graph traversal"
        )
        for mem in resp.memories[:6]:
            tag = "  (linked)" if mem.id in resp.search_around_ids else ""
            print(f"    - [{mem.category.value}] {mem.content[:80]}{tag}")

    if use_llm:
        print("\n=== L3: synthesized concept summaries ===")
        for summary in store.list_summaries()[:6]:
            print(f"  • {summary.concept} (from {summary.memory_count} memories):")
            print(f"      {summary.summary_text[:160]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MintMory with the agentic_support corpus")
    parser.add_argument("--db", default="/tmp/mintmory_corpus.db", help="SQLite path (recreated)")
    parser.add_argument(
        "--no-llm", action="store_true", help="FTS-only, no Ollama summaries/contradictions"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)

    settings = load_settings()
    # Embeddings are pure-Python by default (provider=hashing), fully decoupled from
    # the LLM. The LLM (summaries + contradiction resolution) is opt-in via
    # MINTMORY_LLM_PROVIDER and only used when reachable.
    client = LLMClient(settings.llm)
    use_llm = not args.no_llm and settings.llm.enabled and client.ping()
    embedder = embedder_from_settings(settings.embed)
    print(f"Embedder: {settings.embed.provider.value} (dim {embedder.dimensions})")
    print(f"LLM: {'ON (' + settings.llm.model + ')' if use_llm else 'OFF (graph-only)'}")
    print(
        f"Link cfg: min_shared={settings.link.min_shared_entities} "
        f"df_cap={settings.link.entity_df_cap_ratio} max_per_node={settings.link.max_per_node} "
        f"stoplist={sorted(settings.link.stoplist) or '-'}"
    )

    store = StorageAdapter(str(db_path), embedder=embedder)
    store.initialise()

    print("\nLoading corpus slices:")
    items = load_corpus()
    print(f"\nIngesting {len(items)} records...")
    added = ingest(store, items)
    cats = Counter(rec.category.value for rec in added)
    print("  by category:", ", ".join(f"{k}={v}" for k, v in sorted(cats.items())))

    if use_llm:
        print("\nContradiction detection pass (LLM)...")
        n = detect_contradictions(client, store, added, items)
        print(f"  flagged {n} contradiction(s)")

    print("\nDreaming (run_full: link -> summarize -> resolve -> archive -> rehab)...")
    engine = build_dreaming_engine(
        store,
        settings.llm if use_llm else None,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    report = engine.run_full()
    print(
        f"  new_links={report.new_links} new_summaries={report.new_summaries} "
        f"contradictions_resolved={report.contradictions_resolved} "
        f"archived={report.memories_archived} rehabilitated={report.memories_rehabilitated} "
        f"({report.duration_ms:.0f} ms)"
    )

    demo(store, use_llm)
    print(f"\nDone. Explore it:  MINTMORY_DB={db_path} uv run mintmory search '<query>'")
    store.close()


if __name__ == "__main__":
    main()
