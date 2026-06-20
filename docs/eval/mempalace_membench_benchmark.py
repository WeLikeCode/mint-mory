#!/usr/bin/env python3
"""
mempalace-adapted MemBench benchmark for MintMory.

Replicates mempalace's MemBench methodology (benchmarks/membench_bench.py) on
MintMory's search. MemBench (ACL 2025, https://github.com/import-myself/Membench):
per item, index every conversation turn, query with the QA question, and check
whether an answer-relevant turn (`target_step_id`) is in the top-k (hit@k).

Methodology (identical to mempalace):
  * Data: MemBench `MemData/FirstAgent/<category>.json`, topic-keyed (default
    `movie`). Each item = {message_list (turns/sessions), QA{question,
    target_step_id, ...}}. Turn text = `[time] [User] u [Assistant] a`; each turn
    carries `sid` (or `mid`, else positional) and a `global_idx`.
  * Per item: retrieve top-k turns; hit = target sids intersect retrieved sids OR
    retrieved global indices (mempalace matches against both). Metric = overall
    R@k = hits / items. Headline = movie / all categories / top-5.
  * Embedder: all-MiniLM-L6-v2 — same model as mempalace's run.

NOTE: mempalace's published 80.3% R@5 is its HYBRID mode (name/predicate-boosted
re-rank). We report MintMory vector / hybrid_w1 / hybrid_w<weight> against it;
MintMory's hybrid is generic (no MemBench-specific heuristics).

Usage:
  uv run --no-sync python docs/eval/mempalace_membench_benchmark.py /tmp/membench/MemData/FirstAgent
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from mintmory.core.embedder import LocalEmbedder
from mintmory.core.storage import _MEMORY_COLUMNS, StorageAdapter
from mintmory.core.types import MemoryCategory, MemoryRecord, SearchRequest

CATEGORY_FILES = {
    "simple": "simple.json",
    "highlevel": "highlevel.json",
    "knowledge_update": "knowledge_update.json",
    "comparative": "comparative.json",
    "conditional": "conditional.json",
    "noisy": "noisy.json",
    "aggregative": "aggregative.json",
    "highlevel_rec": "highlevel_rec.json",
    "lowlevel_rec": "lowlevel_rec.json",
    "RecMultiSession": "RecMultiSession.json",
    "post_processing": "post_processing.json",
}


def turn_text(turn: dict) -> str:
    user = turn.get("user") or turn.get("user_message", "")
    asst = turn.get("assistant") or turn.get("assistant_message", "")
    t = turn.get("time", "")
    text = f"[User] {user} [Assistant] {asst}"
    return f"[{t}] {text}" if t else text


def load_items(data_dir: Path, topic: str, limit: int) -> list[dict]:
    items = []
    for cat, fname in CATEGORY_FILES.items():
        fpath = data_dir / fname
        if not fpath.exists():
            continue
        with open(fpath) as f:
            raw = json.load(f)
        for t, topic_items in raw.items():
            if topic and t not in (topic, "roles", "events"):
                continue
            for item in topic_items:
                turns = item.get("message_list", [])
                qa = item.get("QA", {})
                if not turns or not qa:
                    continue
                items.append(
                    {
                        "category": cat,
                        "turns": turns,
                        "question": qa.get("question", ""),
                        "target_step_ids": qa.get("target_step_id", []),
                    }
                )
    return items[:limit] if limit > 0 else items


def index_turns(
    s: StorageAdapter, embedder: LocalEmbedder, message_list: list
) -> dict[str, tuple[int, int]]:
    """Bulk-index all turns (batch embed + executemany) -> mid -> (sid, global_idx).

    Items can carry thousands of turns; per-turn add_memory (one embed + entity
    extraction each) is the bottleneck, so we batch-embed and bulk-insert. The FTS
    + trigram triggers still fire on INSERT; entity extraction is skipped (it does
    not affect FTS/trigram/vector retrieval recall)."""
    sessions = (
        [message_list] if (message_list and isinstance(message_list[0], dict)) else message_list
    )
    texts: list[str] = []
    keys: list[tuple[int, int]] = []
    gidx = 0
    for session in sessions:
        if not isinstance(session, list):
            continue
        for turn in session:
            if not isinstance(turn, dict):
                continue
            sid = turn.get("sid", turn.get("mid"))
            sid = int(sid) if isinstance(sid, (int, float)) else gidx
            texts.append(turn_text(turn)[:10_000])
            keys.append((sid, gidx))
            gidx += 1
    if not texts:
        return {}
    embs = embedder.embed_batch(texts)
    cols = ", ".join(_MEMORY_COLUMNS)
    ph = ", ".join("?" for _ in _MEMORY_COLUMNS)
    mid2key: dict[str, tuple[int, int]] = {}
    rows = []
    for text, key, vec in zip(texts, keys, embs, strict=False):
        rec = MemoryRecord(content=text, category=MemoryCategory.FACT, entity_ids=[])
        mid2key[rec.id] = key
        rows.append(s._memory_row_values(rec, np.asarray(vec, dtype=np.float32).tobytes()))
    with s.transaction() as c:
        c.executemany(f"INSERT INTO memories ({cols}) VALUES ({ph})", rows)
    return mid2key


def target_set(target_step_ids: list) -> set:
    out = set()
    for step in target_step_ids:
        if isinstance(step, list) and step:
            out.add(step[0])
    return out


def hit(top_keys: list[tuple[int, int]], targets: set) -> float:
    sids = {k[0] for k in top_keys}
    gidx = {k[1] for k in top_keys}
    return float(bool(targets & sids) or bool(targets & gidx))


def hybrid_keys(
    s: StorageAdapter, q: str, q_emb: np.ndarray, topk: int, weight: float, mid2key: dict
) -> list[tuple[int, int]]:
    s._vector_rrf_weight = weight
    resp = s.search(SearchRequest(query=q, limit=topk), query_embedding=q_emb)
    return [mid2key[m.id] for m in resp.memories if m.id in mid2key]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--topic", default="movie")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--weight", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("docs/eval/mempalace_membench_results.json"))
    args = ap.parse_args()

    items = load_items(args.data_dir, args.topic, args.limit)
    print(f"=== MintMory × MemBench ({args.topic}, top-{args.top_k}) — {len(items)} items ===")

    embedder = LocalEmbedder()
    variants = ["vector", "hybrid_w1", f"hybrid_w{args.weight:g}"]
    agg: dict[str, list[float]] = {v: [] for v in variants}
    per_cat: dict[str, list[float]] = defaultdict(list)
    t0 = time.time()

    for i, item in enumerate(items):
        s = StorageAdapter(":memory:", embedder=embedder)
        s.initialise()
        mid2key = index_turns(s, embedder, item["turns"])
        if not mid2key:
            continue
        targets = target_set(item["target_step_ids"])
        question = item["question"]
        q_emb = np.asarray(embedder.embed(question), dtype=np.float32)

        vec = s._vector_scores(question, q_emb, max(args.top_k, 50))
        vec_order = sorted(vec, key=vec.get, reverse=True)  # type: ignore[arg-type]
        vec_keys = [mid2key[m] for m in vec_order if m in mid2key][: args.top_k]
        ranked = {
            "vector": vec_keys,
            "hybrid_w1": hybrid_keys(s, question, q_emb, args.top_k, 1.0, mid2key),
            f"hybrid_w{args.weight:g}": hybrid_keys(
                s, question, q_emb, args.top_k, args.weight, mid2key
            ),
        }
        for v, keys in ranked.items():
            agg[v].append(hit(keys, targets))
        per_cat[item["category"]].append(agg["hybrid_w1"][-1])
        s.close()
        if (i + 1) % 500 == 0:
            w1 = np.mean(agg["hybrid_w1"])
            print(f"  {i + 1}/{len(items)}  R@{args.top_k}={w1:.3f}  ({time.time() - t0:.0f}s)")

    results = {
        "config": {
            "embedder": embedder.model_name,
            "topic": args.topic,
            "top_k": args.top_k,
            "items": len(agg["vector"]),
        },
        "recall_at_k": {v: round(float(np.mean(agg[v])), 4) for v in variants},
        "mempalace_published": {"hybrid_movie_top5": 0.803},
        "per_category_hybrid_w1": {
            c: round(float(np.mean(v)), 4) for c, v in sorted(per_cat.items())
        },
    }
    print(f"\n=== RESULTS (R@{args.top_k}) ===")
    for v in variants:
        print(f"{v:<14}{results['recall_at_k'][v]:>9}")
    print(f"{'mempalace hyb':<14}{0.803:>9}  (movie/top-5, published hybrid)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
