#!/usr/bin/env python3
"""
LEANN-adapted recall benchmark for MintMory's hybrid search.

This adapts LEANN's recall@k methodology (benchmarks/run_evaluation.py) onto
MintMory's own search engine. It reuses LEANN's DPR/Natural-Questions evaluation
data (queries + exact-flat ground truth) but indexes a tractable subset of the
DPR corpus into a real MintMory SQLite store and measures MintMory's hybrid
retrieval (FTS5 + trigram + brute-force vector, RRF-fused).

Two ground truths are reported (per the benchmark design):

  * LEANN NQ golden  — recall vs ``flat_results_nq_k3.json`` (top-3 passages an
    exact-flat contriever search returns for each NQ query). Cross-model: the
    golden was built with facebook/contriever-msmarco while MintMory here uses
    all-MiniLM-L6-v2, so absolute numbers are not directly comparable to LEANN's
    ~1.0 — they measure how well MintMory recovers the *same passages*.
  * MintMory exact-flat (self) — recall of the hybrid ranking vs MintMory's own
    pure brute-force cosine top-k over the identical MiniLM embeddings. Measures
    how much the lexical (FTS+trigram) fusion perturbs the dense ranking.

Metrics: recall@3 and recall@10 for each ground truth, plus per-query search
latency and on-disk DB size.

Corpus subset: the union of all golden passages for the evaluated queries plus a
deterministic random sample of distractor passages, up to ``--corpus-size``.
This keeps every golden passage present in the haystack (so recall is meaningful)
while staying CPU-tractable. The haystack is smaller than LEANN's full 2.1M-passage
DPR corpus, so numbers are an upper bound relative to full-corpus difficulty.

Usage:
  uv run --no-sync python docs/eval/leann_recall_benchmark.py \
      --leann-data /tmp/LEANN/benchmarks/data \
      --num-queries 200 --corpus-size 100000

Query text: the bare NQ question is extracted (the "Answer these questions:\\nQ:
... \\nA:" wrapper is stripped) — that is what a real MintMory caller would pass.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from mintmory.core.embedder import EmbedderProtocol, create_embedder
from mintmory.core.storage import _MEMORY_COLUMNS, StorageAdapter
from mintmory.core.types import MemoryCategory, MemoryRecord, SearchRequest

_Q_RE = re.compile(r"Q:\s*(.*?)\s*\nA:", re.DOTALL)


def embed_corpus(embedder: EmbedderProtocol, texts: list[str], workers: int) -> np.ndarray:
    """Embed the corpus. workers>1 fans out over embedder.embed via threads —
    essential for the I/O-bound Ollama embedder (one HTTP call per text); for the
    in-process embedders (local/hashing) the efficient batched path is used."""
    if workers <= 1:
        vecs = embedder.embed_batch(texts)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            vecs = list(ex.map(embedder.embed, texts))
    return np.vstack(vecs).astype(np.float32)


def extract_question(raw: str) -> str:
    """Strip the NQ '...Q: <question>\\nA:' wrapper down to the bare question."""
    m = _Q_RE.search(raw)
    return m.group(1).strip() if m else raw.strip()


def load_queries(path: Path) -> list[str]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line)["query"])
    return out


def build_corpus_ids(
    golden_per_q: list[list[int]], corpus_size: int, total: int, seed: int
) -> tuple[list[int], set[int]]:
    """Golden union + deterministic distractor sample, capped at corpus_size."""
    golden_union: set[int] = set()
    for g in golden_per_q:
        golden_union.update(g)
    rng = random.Random(seed)
    need_distract = max(0, corpus_size - len(golden_union))
    distract: set[int] = set()
    # rejection-sample distractor ids not already golden
    while len(distract) < need_distract:
        cand = rng.randrange(total)
        if cand not in golden_union:
            distract.add(cand)
    corpus_ids = sorted(golden_union | distract)
    return corpus_ids, golden_union


def load_passage_texts(passages_path: Path, needed: set[int]) -> dict[int, str]:
    """Single pass over passages.jsonl; parse only needed lines (id == line no.)."""
    id2text: dict[int, str] = {}
    verified = 0
    with open(passages_path) as f:
        for idx, line in enumerate(f):
            if idx in needed:
                obj = json.loads(line)
                if verified < 5:
                    assert int(obj["id"]) == idx, f"id/lineno mismatch: {obj['id']} != {idx}"
                    verified += 1
                id2text[idx] = obj["text"][:10_000]
                if len(id2text) == len(needed):
                    break
    return id2text


def ingest(
    db_path: Path, embedder: EmbedderProtocol, texts: list[str], embs: np.ndarray, batch: int = 2000
) -> None:
    """Bulk-insert passages as memories with precomputed embeddings (``embs``).

    Faithful to MintMory storage (same schema, FTS + trigram triggers, vec column)
    but bypasses per-item add_memory() — entity extraction is skipped (it does not
    affect FTS/trigram/vector retrieval) so 100k passages stay tractable.
    """
    adapter = StorageAdapter(str(db_path), embedder=embedder)
    adapter.initialise()  # schema.sql: memories + FTS + trigram tables & triggers
    cols = ", ".join(_MEMORY_COLUMNS)
    ph = ", ".join("?" for _ in _MEMORY_COLUMNS)
    n = len(texts)
    for start in range(0, n, batch):
        rows = []
        for j in range(start, min(start + batch, n)):
            rec = MemoryRecord(content=texts[j], category=MemoryCategory.FACT, entity_ids=[])
            blob = embs[j].astype(np.float32).tobytes()
            rows.append(adapter._memory_row_values(rec, blob))
        with adapter.transaction() as c:
            c.executemany(f"INSERT INTO memories ({cols}) VALUES ({ph})", rows)
        print(f"  ingested {min(start + batch, n)}/{n}", end="\r", flush=True)
    print()
    adapter.close()


def recall(retrieved_texts: list[str], golden_texts: set[str], k: int) -> float:
    got = set(retrieved_texts[:k])
    return len(got & golden_texts) / len(golden_texts) if golden_texts else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leann-data", type=Path, default=Path("/tmp/LEANN/benchmarks/data"))
    ap.add_argument("--db", type=Path, default=Path("/tmp/mintmory_leann_bench.db"))
    ap.add_argument("--num-queries", type=int, default=200)
    ap.add_argument("--corpus-size", type=int, default=100_000)
    ap.add_argument("--total-passages", type=int, default=2_101_532)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embedder", choices=["local", "ollama", "hashing"], default="local")
    ap.add_argument("--corpus-workers", type=int, default=1, help=">1 fans out embed (Ollama)")
    ap.add_argument("--out", type=Path, default=Path("docs/eval/leann_recall_results.json"))
    args = ap.parse_args()

    queries_file = args.leann_data / "queries" / "nq_open.jsonl"
    golden_file = args.leann_data / "ground_truth" / "dpr" / "flat_results_nq_k3.json"
    passages_file = (
        args.leann_data / "indices" / "dpr_hnsw" / "dpr_hnsw_IP_M30_efC128.passages.jsonl"
    )

    print("=== MintMory LEANN-adapted recall benchmark ===")
    raw_queries = load_queries(queries_file)[: args.num_queries]
    questions = [extract_question(q) for q in raw_queries]
    with open(golden_file) as f:
        golden_idx = json.load(f)["indices"][: args.num_queries]
    golden_per_q = [[int(x) for x in row[:3]] for row in golden_idx]

    print(f"queries={len(questions)}  building corpus (target {args.corpus_size})...")
    corpus_ids, golden_union = build_corpus_ids(
        golden_per_q, args.corpus_size, args.total_passages, args.seed
    )
    print(f"corpus_ids={len(corpus_ids)} (golden_union={len(golden_union)})")

    print("loading passage texts (single pass over 2.1M jsonl)...")
    t0 = time.time()
    id2text = load_passage_texts(passages_file, set(corpus_ids))
    print(f"  loaded {len(id2text)} texts in {time.time() - t0:.1f}s")

    corpus_ids = [i for i in corpus_ids if i in id2text]
    texts = [id2text[i] for i in corpus_ids]

    if args.db.exists():
        args.db.unlink()
    embedder = create_embedder(args.embedder)
    print(f"embedder={embedder.model_name} dim={embedder.dimensions}")

    print("embedding corpus once (reused for ingest + exact-flat self ground truth)...")
    t0 = time.time()
    corpus_emb = embed_corpus(embedder, texts, args.corpus_workers)  # (N,dim) L2-normed
    print(f"  corpus matrix {corpus_emb.shape} in {time.time() - t0:.1f}s")

    print("ingesting into MintMory...")
    t0 = time.time()
    ingest(args.db, embedder, texts, corpus_emb)
    print(f"  ingest done in {time.time() - t0:.1f}s")

    adapter = StorageAdapter(str(args.db), embedder=embedder)
    adapter.connect()

    topk = 10
    agg = {
        "hybrid_vs_golden@3": [],
        "hybrid_vs_golden@10": [],
        "vector_vs_golden@3": [],
        "vector_vs_golden@10": [],
        "hybrid_vs_self@3": [],
        "hybrid_vs_self@10": [],
    }
    latencies = []

    print(f"evaluating {len(questions)} queries...")
    for qi, question in enumerate(questions):
        q_emb = embedder.embed(question)

        # MintMory hybrid search (FTS + trigram + vector, RRF)
        t0 = time.time()
        resp = adapter.search(SearchRequest(query=question, limit=topk), query_embedding=q_emb)
        latencies.append(time.time() - t0)
        hybrid_texts = [m.content for m in resp.memories]

        # MintMory exact-flat (pure brute-force cosine over the same embeddings)
        sims = corpus_emb @ np.asarray(q_emb, dtype=np.float32)
        top = np.argpartition(-sims, min(topk, len(sims) - 1))[:topk]
        top = top[np.argsort(-sims[top])]
        vector_texts = [texts[p] for p in top]

        # golden texts (must exist in corpus)
        golden_texts = {id2text[g] for g in golden_per_q[qi] if g in id2text}

        agg["hybrid_vs_golden@3"].append(recall(hybrid_texts, golden_texts, 3))
        agg["hybrid_vs_golden@10"].append(recall(hybrid_texts, golden_texts, 10))
        agg["vector_vs_golden@3"].append(recall(vector_texts, golden_texts, 3))
        agg["vector_vs_golden@10"].append(recall(vector_texts, golden_texts, 10))
        agg["hybrid_vs_self@3"].append(len(set(hybrid_texts[:3]) & set(vector_texts[:3])) / 3)
        agg["hybrid_vs_self@10"].append(len(set(hybrid_texts[:10]) & set(vector_texts[:10])) / 10)
        if (qi + 1) % 25 == 0:
            print(f"  {qi + 1}/{len(questions)}", end="\r", flush=True)
    print()

    db_mb = args.db.stat().st_size / 1e6
    results = {
        "config": {
            "embedder": embedder.model_name,
            "dim": embedder.dimensions,
            "num_queries": len(questions),
            "corpus_size": len(texts),
            "golden_union": len(golden_union),
            "db_mb": round(db_mb, 1),
        },
        "metrics": {k: round(float(np.mean(v)), 4) for k, v in agg.items()},
        "latency_ms": {
            "mean": round(float(np.mean(latencies)) * 1000, 2),
            "p50": round(float(np.percentile(latencies, 50)) * 1000, 2),
            "p95": round(float(np.percentile(latencies, 95)) * 1000, 2),
        },
    }
    adapter.close()

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
