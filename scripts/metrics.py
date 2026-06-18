"""
Fast metric harness for MintMory — measures L2 graph quality, entity noise, and
embedding retrieval in SECONDS, without the ~50-min L3 summary phase.

Subcommands:
  graph  — link count, degree distribution, % links from top-K entities, noise
           entities, search-around breadth, and a precision/recall guardrail.
  embed  — recall@10 (vector-only, FTS-only, hybrid) on the labelled probe set,
           plus FTS↔vector top-10 agreement (Jaccard).

Both print a JSON object (last line) AND a human table, so the "after" cells in
docs/EXPERIMENTS.md can be pasted directly. Run after building a DB with
scripts/seed_corpus.py (env vars select provider + linking parameters).

  uv run python scripts/seed_corpus.py --db /tmp/mm_fast.db --no-llm
  uv run python scripts/metrics.py graph --db /tmp/mm_fast.db --probe docs/eval/probe_queries.json
  uv run python scripts/metrics.py embed --db /tmp/mm_fast.db --probe docs/eval/probe_queries.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mintmory.core.config import load_settings  # noqa: E402
from mintmory.core.embedder import embedder_from_settings  # noqa: E402
from mintmory.core.storage import StorageAdapter  # noqa: E402
from mintmory.core.types import ConceptLinkType, SearchAroundSpec, SearchRequest  # noqa: E402

NOISE = {"all", "api", "backend", "ing", "space"}


def _probe(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    return list(data.get("queries", []))


def _resolve_relevant(conn: sqlite3.Connection, substrings: list[str]) -> set[str]:
    """Memory ids (active, non-archived) whose content contains any substring."""
    ids: set[str] = set()
    rows = conn.execute("SELECT id, lower(content) c FROM memories WHERE is_archived=0").fetchall()
    subs = [s.lower() for s in substrings]
    for mid, content in rows:
        if any(s in content for s in subs):
            ids.add(mid)
    return ids


def graph_metrics(db: str, probe_path: str | None, top_k: int) -> dict[str, Any]:
    settings = load_settings()
    store = StorageAdapter(db, embedder=embedder_from_settings(settings.embed))
    conn = store.connect()

    link_count = conn.execute("SELECT count(*) FROM concept_links").fetchone()[0]
    active = conn.execute(
        "SELECT count(*) FROM memories WHERE is_active=1 AND is_archived=0"
    ).fetchone()[0]
    deg_rows = conn.execute(
        "SELECT mid, count(*) d FROM ("
        "  SELECT source_memory_id mid FROM concept_links "
        "  UNION ALL SELECT target_memory_id mid FROM concept_links) GROUP BY mid"
    ).fetchall()
    degs = sorted(r[1] for r in deg_rows)
    by_entity = conn.execute(
        "SELECT entity, count(*) n FROM concept_links WHERE entity!='' "
        "GROUP BY entity ORDER BY n DESC"
    ).fetchall()
    top = [(e, n) for e, n in by_entity[:10]]
    pct_top_k = (
        round(100.0 * sum(n for _, n in by_entity[:top_k]) / link_count, 1) if link_count else 0.0
    )
    noise_present = sorted({e for e, _ in by_entity if e in NOISE})

    breadth: list[dict[str, Any]] = []
    for q in _probe(probe_path):
        relevant = _resolve_relevant(conn, q.get("relevant_substrings", []))
        resp = store.search(
            SearchRequest(
                query=q["query"],
                limit=10,
                search_around=SearchAroundSpec(depth=2, link_types=[ConceptLinkType.RELATES_TO]),
            )
        )
        returned = {m.id for m in resp.memories}
        primary5 = [m.id for m in resp.memories if m.id not in resp.search_around_ids][:5]
        breadth.append(
            {
                "query": q["query"],
                "graph_added": len(resp.search_around_ids),
                "breadth_pct": round(100.0 * len(resp.search_around_ids) / active, 1)
                if active
                else 0.0,
                "precision_at_5": round(len(set(primary5) & relevant) / 5, 2),
                "recall_in_union": round(len(returned & relevant) / len(relevant), 2)
                if relevant
                else None,
            }
        )
    store.close()
    mean_breadth = round(statistics.mean(b["breadth_pct"] for b in breadth), 1) if breadth else None
    return {
        "mode": "graph",
        "config": {
            "embed_provider": settings.embed.provider.value,
            "link_min_shared": settings.link.min_shared_entities,
            "link_df_cap": settings.link.entity_df_cap_ratio,
            "link_max_per_node": settings.link.max_per_node,
            "link_stoplist": sorted(settings.link.stoplist),
        },
        "active_memories": active,
        "link_count": link_count,
        "linked_nodes": len(degs),
        "degree_avg": round(statistics.mean(degs), 1) if degs else 0,
        "degree_median": degs[len(degs) // 2] if degs else 0,
        "degree_max": degs[-1] if degs else 0,
        f"pct_links_top_{top_k}_entities": pct_top_k,
        "links_per_entity_top10": top,
        "noise_entities_present": noise_present,
        "mean_search_around_breadth_pct": mean_breadth,
        "search_around": breadth,
    }


def _recall(top: list[str], relevant: set[str]) -> float:
    return round(len(set(top) & relevant) / len(relevant), 2) if relevant else 0.0


def _fts_top(conn: sqlite3.Connection, query: str, k: int) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", query.lower())
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    try:
        rows = conn.execute(
            "SELECT m.id FROM memories_fts JOIN memories m ON m.rowid=memories_fts.rowid "
            "WHERE memories_fts MATCH ? AND m.is_archived=0 ORDER BY rank LIMIT ?",
            (match, k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def embed_metrics(db: str, probe_path: str | None) -> dict[str, Any]:
    settings = load_settings()
    embedder = embedder_from_settings(settings.embed)
    store = StorageAdapter(db, embedder=embedder)
    conn = store.connect()
    vec_ok = store._vector_search_available()

    rows: list[dict[str, Any]] = []
    for q in _probe(probe_path):
        relevant = _resolve_relevant(conn, q.get("relevant_substrings", []))
        if not relevant:
            continue
        hybrid = [m.id for m in store.search(SearchRequest(query=q["query"], limit=10)).memories]
        fts = _fts_top(conn, q["query"], 10)
        vec: list[str] = []
        if vec_ok:
            blob = embedder.embed(q["query"]).astype("float32").tobytes()
            vrows = conn.execute(
                "SELECT id FROM memories WHERE is_archived=0 AND embedding IS NOT NULL "
                "ORDER BY vec_distance_cosine(embedding, ?) LIMIT 10",
                (blob,),
            ).fetchall()
            vec = [r[0] for r in vrows]

        jac = (
            round(len(set(fts) & set(vec)) / len(set(fts) | set(vec)), 2) if (fts and vec) else None
        )
        rows.append(
            {
                "query": q["query"],
                "relevant": len(relevant),
                "recall10_fts": _recall(fts, relevant),
                "recall10_vector": _recall(vec, relevant) if vec_ok else None,
                "recall10_hybrid": _recall(hybrid, relevant),
                "fts_vector_jaccard": jac,
            }
        )
    store.close()

    def mean(key: str) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(statistics.mean(vals), 3) if vals else None

    return {
        "mode": "embed",
        "config": {"embed_provider": settings.embed.provider.value, "dim": embedder.dimensions},
        "vector_search_available": vec_ok,
        "queries": len(rows),
        "mean_recall10_fts": mean("recall10_fts"),
        "mean_recall10_vector": mean("recall10_vector"),
        "mean_recall10_hybrid": mean("recall10_hybrid"),
        "mean_fts_vector_jaccard": mean("fts_vector_jaccard"),
        "per_query": rows,
    }


def _print_table(result: dict[str, Any]) -> None:
    print(f"\n=== metrics: {result['mode']} ===")
    for k, v in result.items():
        if k in ("search_around", "per_query", "links_per_entity_top10", "mode"):
            continue
        print(f"  {k}: {v}")
    if result["mode"] == "graph":
        print(
            "  links_per_entity_top10:",
            ", ".join(f"{e}={n}" for e, n in result["links_per_entity_top10"]),
        )
        for b in result["search_around"]:
            print(
                f"    [{b['breadth_pct']:>5}% breadth] p@5={b['precision_at_5']} "
                f"recall_union={b['recall_in_union']}  {b['query']!r}"
            )
    else:
        for r in result["per_query"]:
            print(
                f"    fts={r['recall10_fts']} vec={r['recall10_vector']} "
                f"hybrid={r['recall10_hybrid']} jac={r['fts_vector_jaccard']}  {r['query']!r}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="MintMory fast metric harness")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("graph", "embed"):
        p = sub.add_parser(name)
        p.add_argument("--db", default="/tmp/mm_fast.db")
        p.add_argument("--probe", default="docs/eval/probe_queries.json")
        if name == "graph":
            p.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()

    if args.cmd == "graph":
        result = graph_metrics(args.db, args.probe, args.top_k)
    else:
        result = embed_metrics(args.db, args.probe)
    _print_table(result)
    print("\nJSON:", json.dumps(result))


if __name__ == "__main__":
    main()
