#!/usr/bin/env python3
"""
RRF-fusion investigation for the MintMory recall finding (docs/EXPERIMENTS.md §10).

The LEANN-adapted benchmark showed MintMory's hybrid search (unweighted RRF over
FTS + trigram + vector) has *lower* recall@3 than pure vector at 100k scale —
the two lexical rank-lists can outvote the correct dense hit at the head.

This script reuses the same corpus/queries/ground-truth and the SAME ingested
store, then re-fuses the per-query component score dicts (``_fts_scores`` /
``_trigram_scores`` / ``_vector_scores``) under several strategies, measuring
recall@3/@10 vs LEANN's NQ golden for each — to find a fusion that recovers the
vector-only head without losing the lexical tail.

Strategies:
  * vector_only          — brute-force cosine top-k (the bar to recover)
  * rrf_k60 (default)    — current MintMory fusion: unweighted RRF, k=60
  * wrrf_v{2,3,5}        — weighted RRF: vector contributes w/(k+rank), lexical 1/(k+rank)
  * rerank_n{20,50}      — take RRF top-N candidates, reorder by cosine, take top-k

Run (after the local-embedder benchmark deps are present):
  uv run --no-sync python docs/eval/rrf_investigation.py --num-queries 200 --corpus-size 100000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leann_recall_benchmark as bench  # noqa: E402
from mintmory.core.scoring import rrf_merge  # noqa: E402
from mintmory.core.storage import StorageAdapter  # noqa: E402


def wrrf(sources: list[tuple[dict[str, float], float]], k: int = 60) -> dict[str, float]:
    """Weighted RRF: each source contributes weight/(k+rank)."""
    merged: dict[str, float] = {}
    for scores, w in sources:
        if not scores:
            continue
        for rank, doc in enumerate(sorted(scores, key=scores.get, reverse=True), start=1):  # type: ignore[arg-type]
            merged[doc] = merged.get(doc, 0.0) + w / (k + rank)
    return merged


def topk_ids(scores: dict[str, float], k: int) -> list[str]:
    return sorted(scores, key=scores.get, reverse=True)[:k]  # type: ignore[arg-type]


def cosine_rerank(
    cand_ids: list[str], k: int, q_emb: np.ndarray, mid2vec: dict[str, np.ndarray]
) -> list[str]:
    """Reorder RRF candidate ids by cosine to the query, take top-k."""
    scored = [(float(mid2vec[c] @ q_emb), c) for c in cand_ids if c in mid2vec]
    scored.sort(reverse=True)
    return [c for _, c in scored[:k]]


def recall_ids(ranked: list[str], golden_texts: set[str], id2text: dict[str, str], k: int) -> float:
    got = {id2text[i] for i in ranked[:k] if i in id2text}
    return len(got & golden_texts) / len(golden_texts) if golden_texts else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leann-data", type=Path, default=Path("/tmp/LEANN/benchmarks/data"))
    ap.add_argument("--db", type=Path, default=Path("/tmp/mintmory_rrf_invest.db"))
    ap.add_argument("--num-queries", type=int, default=200)
    ap.add_argument("--corpus-size", type=int, default=100_000)
    ap.add_argument("--total-passages", type=int, default=2_101_532)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("docs/eval/rrf_investigation_results.json"))
    args = ap.parse_args()

    qf = args.leann_data / "queries" / "nq_open.jsonl"
    gf = args.leann_data / "ground_truth" / "dpr" / "flat_results_nq_k3.json"
    pf = args.leann_data / "indices" / "dpr_hnsw" / "dpr_hnsw_IP_M30_efC128.passages.jsonl"

    questions = [bench.extract_question(q) for q in bench.load_queries(qf)[: args.num_queries]]
    with open(gf) as f:
        golden_idx = json.load(f)["indices"][: args.num_queries]
    golden_per_q = [[int(x) for x in row[:3]] for row in golden_idx]

    corpus_ids, _ = bench.build_corpus_ids(
        golden_per_q, args.corpus_size, args.total_passages, args.seed
    )
    passage_text = bench.load_passage_texts(pf, set(corpus_ids))
    corpus_ids = [i for i in corpus_ids if i in passage_text]
    texts = [passage_text[i] for i in corpus_ids]

    if args.db.exists():
        args.db.unlink()
    embedder = bench.create_embedder("local")
    print(f"embedder={embedder.model_name} corpus={len(texts)}")
    corpus_emb = bench.embed_corpus(embedder, texts, workers=1)
    print("ingesting...")
    bench.ingest(args.db, embedder, texts, corpus_emb)

    adapter = StorageAdapter(str(args.db), embedder=embedder)
    adapter.connect()

    # Map MintMory memory_id -> (text, embedding-row) for fusion + cosine rerank.
    rows = adapter.connect().execute("SELECT id, content, embedding FROM memories").fetchall()
    mid2text = {r["id"]: r["content"] for r in rows}
    mid2vec = {
        r["id"]: np.frombuffer(r["embedding"], dtype=np.float32) for r in rows if r["embedding"]
    }

    pool = 50  # mirrors search() candidate pool for limit=10
    strategies = [
        "vector_only",
        "rrf_k60",
        "wrrf_v2",
        "wrrf_v3",
        "wrrf_v5",
        "rerank_n20",
        "rerank_n50",
    ]
    agg: dict[str, dict[int, list[float]]] = {s: {3: [], 10: []} for s in strategies}

    print(f"evaluating {len(questions)} queries x {len(strategies)} strategies...")
    for qi, question in enumerate(questions):
        q_emb = np.asarray(embedder.embed(question), dtype=np.float32)
        fts = adapter._fts_scores(question, pool)
        tri = adapter._trigram_scores(question, pool)
        vec = adapter._vector_scores(question, q_emb, pool)
        golden_texts = {passage_text[g] for g in golden_per_q[qi] if g in passage_text}

        rrf_default = rrf_merge(*[s for s in (fts, tri, vec) if s])
        ranked = {
            "vector_only": topk_ids(vec, 10),
            "rrf_k60": topk_ids(rrf_default, 10),
            "wrrf_v2": topk_ids(wrrf([(fts, 1.0), (tri, 1.0), (vec, 2.0)]), 10),
            "wrrf_v3": topk_ids(wrrf([(fts, 1.0), (tri, 1.0), (vec, 3.0)]), 10),
            "wrrf_v5": topk_ids(wrrf([(fts, 1.0), (tri, 1.0), (vec, 5.0)]), 10),
            "rerank_n20": cosine_rerank(topk_ids(rrf_default, 20), 10, q_emb, mid2vec),
            "rerank_n50": cosine_rerank(topk_ids(rrf_default, 50), 10, q_emb, mid2vec),
        }
        for s, ids in ranked.items():
            agg[s][3].append(recall_ids(ids, golden_texts, mid2text, 3))
            agg[s][10].append(recall_ids(ids, golden_texts, mid2text, 10))
        if (qi + 1) % 25 == 0:
            print(f"  {qi + 1}/{len(questions)}", end="\r", flush=True)
    print()
    adapter.close()

    results = {
        "config": {"num_queries": len(questions), "corpus_size": len(texts), "pool": pool},
        "recall": {
            s: {
                "@3": round(float(np.mean(agg[s][3])), 4),
                "@10": round(float(np.mean(agg[s][10])), 4),
            }
            for s in strategies
        },
    }
    print("\n=== RRF INVESTIGATION RESULTS (recall vs LEANN NQ golden) ===")
    print(f"{'strategy':<14}{'recall@3':>10}{'recall@10':>11}")
    for s in strategies:
        print(f"{s:<14}{results['recall'][s]['@3']:>10}{results['recall'][s]['@10']:>11}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
