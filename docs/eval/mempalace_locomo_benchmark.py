#!/usr/bin/env python3
"""
mempalace-adapted LoCoMo benchmark for MintMory.

Replicates mempalace's LoCoMo *raw* methodology (benchmarks/locomo_bench.py) on
MintMory's search, so numbers sit next to mempalace's published table (README:
session/top-10 raw = 60.3% avg recall; dialog = 48.0%; hybrid v5 = 88.9%).

Methodology (identical to mempalace raw):
  * 10 conversations; each has `conversation.session_N` (lists of {speaker, dia_id,
    text}) and ~199 `qa` items (question, answer, evidence=[dia_id...], category).
  * Session granularity: one doc per session = the dialog turns joined as
    `Speaker said, "text"`; corpus id = `session_N`. Dialog granularity: one doc
    per turn, id = `dia_id` (e.g. "D1:3").
  * For each question, retrieve top-k; recall = fraction of the question's evidence
    ids (mapped to session/dialog ids) that appear in the retrieved top-k
    (mempalace `compute_retrieval_recall`; empty evidence => 1.0). Averaged over
    all 1986 questions. Headline is session granularity, top-10.
  * Embedder: all-MiniLM-L6-v2 — same model as mempalace's raw run.

MintMory variants (identical corpus/queries): vector (pure cosine), hybrid_w1
(default), hybrid_w<weight> (MM-22 vector_rrf_weight).

Usage:
  uv run --no-sync python docs/eval/mempalace_locomo_benchmark.py \
      /tmp/locomo/data/locomo10.json --granularity session --top-k 10
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from mintmory.core.embedder import LocalEmbedder
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import SearchRequest

_DIA_RE = re.compile(r"D(\d+):")


def load_sessions(conversation: dict) -> list[dict]:
    sessions = []
    n = 1
    while f"session_{n}" in conversation:
        sessions.append(
            {
                "session_num": n,
                "date": conversation.get(f"session_{n}_date_time", ""),
                "dialogs": conversation[f"session_{n}"],
            }
        )
        n += 1
    return sessions


def build_corpus(sessions: list[dict], granularity: str) -> tuple[list[str], list[str]]:
    docs, ids = [], []
    for sess in sessions:
        if granularity == "session":
            text = "\n".join(
                f'{d.get("speaker", "?")} said, "{d.get("text", "")}"' for d in sess["dialogs"]
            )
            docs.append(text)
            ids.append(f"session_{sess['session_num']}")
        else:
            for d in sess["dialogs"]:
                docs.append(f'{d.get("speaker", "?")} said, "{d.get("text", "")}"')
                ids.append(d.get("dia_id", f"D{sess['session_num']}:?"))
    return docs, ids


def evidence_ids(evidence: list[str], granularity: str) -> set[str]:
    if granularity == "session":
        out = set()
        for eid in evidence:
            m = _DIA_RE.match(eid)
            if m:
                out.add(f"session_{m.group(1)}")
        return out
    return set(evidence)


def recall(retrieved: list[str], evidence: set[str]) -> float:
    if not evidence:
        return 1.0  # mempalace convention
    return sum(1 for e in evidence if e in retrieved) / len(evidence)


def hybrid_ids(
    s: StorageAdapter, q: str, q_emb: np.ndarray, topk: int, weight: float, mid2cid: dict
) -> list[str]:
    s._vector_rrf_weight = weight
    resp = s.search(SearchRequest(query=q, limit=topk), query_embedding=q_emb)
    return [mid2cid.get(m.id, "") for m in resp.memories]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file", type=Path)
    ap.add_argument("--granularity", choices=["session", "dialog"], default="session")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--weight", type=float, default=3.0)
    ap.add_argument("--out", type=Path, default=Path("docs/eval/mempalace_locomo_results.json"))
    args = ap.parse_args()

    with open(args.data_file) as f:
        data = json.load(f)
    print(f"=== MintMory × LoCoMo (mempalace-adapted, {args.granularity}, top-{args.top_k}) ===")

    embedder = LocalEmbedder()
    variants = ["vector", "hybrid_w1", f"hybrid_w{args.weight:g}"]
    agg: dict[str, list[float]] = {v: [] for v in variants}
    per_cat: dict[int, list[float]] = defaultdict(list)  # hybrid_w<weight> by category
    t0 = time.time()

    for ci, conv in enumerate(data):
        sessions = load_sessions(conv["conversation"])
        docs, cids = build_corpus(sessions, args.granularity)
        if not docs:
            continue
        s = StorageAdapter(":memory:", embedder=embedder)
        s.initialise()
        mid2cid: dict[str, str] = {}
        for doc, cid in zip(docs, cids, strict=False):
            rec = s.add_memory(content=doc[:10_000], category="fact", metadata={"cid": cid})
            mid2cid[rec.id] = cid

        for qa in conv["qa"]:
            question = qa["question"]
            ev = evidence_ids(qa.get("evidence", []), args.granularity)
            q_emb = np.asarray(embedder.embed(question), dtype=np.float32)

            vec = s._vector_scores(question, q_emb, max(args.top_k, 50))
            vec_ids = [mid2cid[m] for m in sorted(vec, key=vec.get, reverse=True)][: args.top_k]  # type: ignore[arg-type]
            ranked = {
                "vector": vec_ids,
                "hybrid_w1": hybrid_ids(s, question, q_emb, args.top_k, 1.0, mid2cid),
                f"hybrid_w{args.weight:g}": hybrid_ids(
                    s, question, q_emb, args.top_k, args.weight, mid2cid
                ),
            }
            for v, top in ranked.items():
                agg[v].append(recall(top, ev))
            per_cat[qa.get("category", -1)].append(agg[f"hybrid_w{args.weight:g}"][-1])
        s.close()
        w1 = np.mean(agg["hybrid_w1"])
        print(f"  conv {ci + 1}/{len(data)}  hybrid_w1 avg={w1:.3f}  ({time.time() - t0:.0f}s)")

    results = {
        "config": {
            "embedder": embedder.model_name,
            "granularity": args.granularity,
            "top_k": args.top_k,
            "questions": len(agg["vector"]),
        },
        "avg_recall": {v: round(float(np.mean(agg[v])), 4) for v in variants},
        "mempalace_published": {"raw_session_top10": 0.603, "hybrid_v5_session": 0.889},
        "per_category_hybrid": {
            str(c): round(float(np.mean(v)), 4) for c, v in sorted(per_cat.items())
        },
    }
    print("\n=== RESULTS (avg recall) ===")
    for v in variants:
        print(f"{v:<14}{results['avg_recall'][v]:>9}")
    print(f"{'mempalace raw':<14}{0.603:>9}  (session/top-10, published)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
