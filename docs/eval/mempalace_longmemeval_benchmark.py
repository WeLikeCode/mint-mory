#!/usr/bin/env python3
"""
mempalace-adapted LongMemEval benchmark for MintMory.

Replicates mempalace's LongMemEval *raw* methodology (benchmarks/longmemeval_bench.py)
on MintMory's own search engine, so the numbers sit next to mempalace's published
table (docs: mempalace README — raw 96.6% R@5 / 98.2% R@10 with all-MiniLM-L6-v2).

Methodology (identical to mempalace raw, session granularity):
  * For each of the 500 questions, build a fresh store from that question's
    `haystack_sessions`; one document per session = the session's USER turns joined
    with newlines; the document's id carries the session id (`answer_session_ids`
    is the ground truth).
  * Query with `entry["question"]`; metric is `recall_any@k` = top-k retrieved
    sessions contain ANY answer session. (mempalace's headline metric.)
  * Embedder: all-MiniLM-L6-v2 — the SAME model mempalace's raw run uses, so the
    comparison isolates the retrieval engine, not the embedding model.

MintMory variants reported (all on the identical corpus/queries):
  * vector       — pure brute-force cosine (method-match to mempalace's raw semantic)
  * hybrid_w1    — MintMory hybrid (FTS+trigram+vector RRF), default weight 1.0
  * hybrid_w3    — MintMory hybrid with the MM-22 vector_rrf_weight=3.0 fix

Usage:
  uv run --no-sync python docs/eval/mempalace_longmemeval_benchmark.py \
      /tmp/lme-data/longmemeval_s_cleaned.json --limit 0
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from mintmory.core.embedder import LocalEmbedder
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import SearchRequest


def session_doc(session: list[dict]) -> str:
    """One document per session = the user turns joined (mempalace raw, session granularity)."""
    return "\n".join(t["content"] for t in session if t["role"] == "user")


def recall_any(top_sids: list[str], answer_sids: set[str], k: int) -> float:
    return float(bool(set(top_sids[:k]) & answer_sids))


def hybrid_sids(
    s: StorageAdapter, question: str, q_emb: np.ndarray, topk: int, weight: float
) -> list[str]:
    """Run MintMory hybrid search at the given vector RRF weight; return ranked sids."""
    s._vector_rrf_weight = weight
    resp = s.search(SearchRequest(query=question, limit=topk), query_embedding=q_emb)
    return [m.metadata.get("sid", "") for m in resp.memories]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="0 = all questions")
    ap.add_argument("--weight", type=float, default=3.0, help="MM-22 vector_rrf_weight variant")
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument(
        "--out", type=Path, default=Path("docs/eval/mempalace_longmemeval_results.json")
    )
    args = ap.parse_args()

    with open(args.data_file) as f:
        data = json.load(f)
    if args.limit:
        data = data[: args.limit]
    print(
        f"=== MintMory × LongMemEval (mempalace-adapted, raw/session) — {len(data)} questions ==="
    )

    embedder = LocalEmbedder()
    variants = ["vector", "hybrid_w1", f"hybrid_w{args.weight:g}"]
    agg: dict[str, dict[int, list[float]]] = {v: {5: [], 10: []} for v in variants}
    per_type: dict[str, list[float]] = defaultdict(list)  # hybrid_w3 recall_any@5 by qtype
    t0 = time.time()

    for qi, entry in enumerate(data):
        answer_sids = set(entry["answer_session_ids"])
        sessions = entry["haystack_sessions"]
        sids = entry["haystack_session_ids"]
        question = entry["question"]

        docs, doc_sids = [], []
        for session, sid in zip(sessions, sids, strict=False):
            doc = session_doc(session)
            if doc:
                docs.append(doc)
                doc_sids.append(sid)
        if not docs:
            continue

        s = StorageAdapter(":memory:", embedder=embedder)
        s.initialise()
        mid2sid: dict[str, str] = {}
        for doc, sid in zip(docs, doc_sids, strict=False):
            rec = s.add_memory(content=doc[:10_000], category="fact", metadata={"sid": sid})
            mid2sid[rec.id] = sid

        q_emb = np.asarray(embedder.embed(question), dtype=np.float32)

        # vector-only (pure cosine) — method-match to mempalace raw
        vec = s._vector_scores(question, q_emb, max(args.topk, 50))
        vec_sids = [mid2sid[mid] for mid in sorted(vec, key=vec.get, reverse=True)]  # type: ignore[arg-type]

        ranked = {
            "vector": vec_sids,
            "hybrid_w1": hybrid_sids(s, question, q_emb, args.topk, 1.0),
            f"hybrid_w{args.weight:g}": hybrid_sids(s, question, q_emb, args.topk, args.weight),
        }
        for v, top in ranked.items():
            agg[v][5].append(recall_any(top, answer_sids, 5))
            agg[v][10].append(recall_any(top, answer_sids, 10))
        per_type[entry.get("question_type", "?")].append(agg[f"hybrid_w{args.weight:g}"][5][-1])
        s.close()

        if (qi + 1) % 25 == 0:
            r5 = np.mean(agg["hybrid_w1"][5])
            print(f"  {qi + 1}/{len(data)}  hybrid_w1 R@5={r5:.3f}  ({time.time() - t0:.0f}s)")

    n = len(agg["vector"][5])
    results = {
        "config": {"embedder": embedder.model_name, "questions": n, "topk": args.topk},
        "metrics": {
            v: {
                "recall_any@5": round(float(np.mean(agg[v][5])), 4),
                "recall_any@10": round(float(np.mean(agg[v][10])), 4),
            }
            for v in variants
        },
        "mempalace_published": {"raw": {"recall_any@5": 0.966, "recall_any@10": 0.982}},
        "per_type_recall_any@5_hybrid": {
            t: round(float(np.mean(v)), 4) for t, v in sorted(per_type.items())
        },
    }
    print("\n=== RESULTS (recall_any) ===")
    print(f"{'variant':<14}{'R@5':>9}{'R@10':>9}")
    for v in variants:
        m = results["metrics"][v]
        print(f"{v:<14}{m['recall_any@5']:>9}{m['recall_any@10']:>9}")
    print(f"{'mempalace raw':<14}{0.966:>9}{0.982:>9}  (published)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
