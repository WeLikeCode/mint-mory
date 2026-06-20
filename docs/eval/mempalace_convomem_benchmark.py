#!/usr/bin/env python3
"""
mempalace-adapted ConvoMem benchmark for MintMory.

Replicates mempalace's ConvoMem *raw* methodology (benchmarks/convomem_bench.py)
on MintMory's search, comparing against mempalace's published 92.9% avg recall
(raw, all categories, 50/cat, top-10).

Methodology (identical to mempalace raw):
  * Data: Salesforce/ConvoMem `core_benchmark/evidence_questions/<category>/1_evidence`
    (6 categories), downloaded on demand from the HF Hub. The loader functions are
    copied verbatim from mempalace's harness so the item selection is IDENTICAL
    (same file order, first `limit` items per category).
  * Per evidence item: corpus = one doc per message across the item's conversations;
    query = item question; retrieve top-k messages; recall = fraction of the item's
    evidence message texts found in the retrieved top-k via substring match (either
    direction), exactly as mempalace's `retrieve_for_item`. Empty evidence => 1.0.
  * Embedder: all-MiniLM-L6-v2 — same model as mempalace's raw run.

MintMory variants (identical corpus/queries): vector (pure cosine), hybrid_w1
(default), hybrid_w<weight> (MM-22 vector_rrf_weight).

Usage:
  uv run --no-sync python docs/eval/mempalace_convomem_benchmark.py --limit 50 --top-k 10
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
from mintmory.core.embedder import LocalEmbedder
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import SearchRequest

# --- mempalace loader (copied verbatim for identical item selection) ----------
HF_BASE = "https://huggingface.co/datasets/Salesforce/ConvoMem/resolve/main/core_benchmark/evidence_questions"
CATEGORIES = {
    "user_evidence": "User Facts",
    "assistant_facts_evidence": "Assistant Facts",
    "changing_evidence": "Changing Facts",
    "abstention_evidence": "Abstention",
    "preference_evidence": "Preferences",
    "implicit_connection_evidence": "Implicit Connections",
}


def download_evidence_file(category: str, subpath: str, cache_dir: str) -> dict | None:
    url = f"{HF_BASE}/{category}/{subpath}"
    cache_path = os.path.join(cache_dir, category, subpath.replace("/", "_"))
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    try:
        urllib.request.urlretrieve(url, cache_path)  # noqa: S310
        with open(cache_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"    failed {url}: {e}")
        return None


def discover_files(category: str, cache_dir: str) -> list[str]:
    api = f"https://huggingface.co/api/datasets/Salesforce/ConvoMem/tree/main/core_benchmark/evidence_questions/{category}/1_evidence"
    cache_path = os.path.join(cache_dir, f"{category}_filelist.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    try:
        with urllib.request.urlopen(urllib.request.Request(api), timeout=15) as resp:  # noqa: S310
            files = json.loads(resp.read())
        paths = [f["path"].split(f"{category}/")[1] for f in files if f["path"].endswith(".json")]
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(paths, f)
        return paths
    except Exception as e:
        print(f"    list failed {category}: {e}")
        return []


def load_evidence_items(categories: list[str], limit: int, cache_dir: str) -> list[dict]:
    all_items = []
    for category in categories:
        files = discover_files(category, cache_dir)
        items_for_cat: list[dict] = []
        for fpath in files:
            if len(items_for_cat) >= limit:
                break
            data = download_evidence_file(category, fpath, cache_dir)
            if data and "evidence_items" in data:
                for item in data["evidence_items"]:
                    item["_category_key"] = category
                    items_for_cat.append(item)
        all_items.extend(items_for_cat[:limit])
        print(f"  {CATEGORIES.get(category, category)}: {len(items_for_cat[:limit])} items")
    return all_items


# --- MintMory retrieval -------------------------------------------------------
def item_corpus(item: dict) -> list[str]:
    corpus = []
    for conv in item.get("conversations", []):
        for msg in conv.get("messages", []):
            corpus.append(msg["text"])
    return corpus


def match_recall(retrieved_texts: list[str], evidence_texts: set[str]) -> float:
    if not evidence_texts:
        return 1.0
    found = 0
    for ev in evidence_texts:
        if any(ev in rt or rt in ev for rt in retrieved_texts):
            found += 1
    return found / len(evidence_texts)


def hybrid_texts(
    s: StorageAdapter, q: str, q_emb: np.ndarray, topk: int, weight: float
) -> list[str]:
    s._vector_rrf_weight = weight
    resp = s.search(SearchRequest(query=q, limit=topk), query_embedding=q_emb)
    return [m.content.strip().lower() for m in resp.memories]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50, help="items per category")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--weight", type=float, default=3.0)
    ap.add_argument("--cache-dir", default="/tmp/convomem_cache")
    ap.add_argument("--out", type=Path, default=Path("docs/eval/mempalace_convomem_results.json"))
    args = ap.parse_args()

    print("=== MintMory × ConvoMem (mempalace-adapted, raw, per-message) ===")
    items = load_evidence_items(list(CATEGORIES), args.limit, args.cache_dir)
    print(f"  total items: {len(items)}")

    embedder = LocalEmbedder()
    variants = ["vector", "hybrid_w1", f"hybrid_w{args.weight:g}"]
    agg: dict[str, list[float]] = {v: [] for v in variants}
    per_cat: dict[str, list[float]] = defaultdict(list)
    t0 = time.time()

    for i, item in enumerate(items):
        corpus = item_corpus(item)
        if not corpus:
            continue
        ev_texts = {e["text"].strip().lower() for e in item.get("message_evidences", [])}
        question = item["question"]

        s = StorageAdapter(":memory:", embedder=embedder)
        s.initialise()
        mid2text: dict[str, str] = {}
        for msg in corpus:
            rec = s.add_memory(content=msg[:10_000], category="fact")
            mid2text[rec.id] = msg.strip().lower()

        q_emb = np.asarray(embedder.embed(question), dtype=np.float32)
        vec = s._vector_scores(question, q_emb, max(args.top_k, 50))
        vec_texts = [mid2text[m] for m in sorted(vec, key=vec.get, reverse=True)][: args.top_k]  # type: ignore[arg-type]

        ranked = {
            "vector": vec_texts,
            "hybrid_w1": hybrid_texts(s, question, q_emb, args.top_k, 1.0),
            f"hybrid_w{args.weight:g}": hybrid_texts(s, question, q_emb, args.top_k, args.weight),
        }
        for v, top in ranked.items():
            agg[v].append(match_recall(top, ev_texts))
        per_cat[item.get("_category_key", "?")].append(agg["hybrid_w1"][-1])
        s.close()
        if (i + 1) % 50 == 0:
            w1 = np.mean(agg["hybrid_w1"])
            print(f"  {i + 1}/{len(items)}  hybrid_w1 avg={w1:.3f}  ({time.time() - t0:.0f}s)")

    results = {
        "config": {
            "embedder": embedder.model_name,
            "items": len(agg["vector"]),
            "top_k": args.top_k,
        },
        "avg_recall": {v: round(float(np.mean(agg[v])), 4) for v in variants},
        "mempalace_published": {"raw_all_top10": 0.929},
        "per_category_hybrid_w1": {
            c: round(float(np.mean(v)), 4) for c, v in sorted(per_cat.items())
        },
    }
    print("\n=== RESULTS (avg recall) ===")
    for v in variants:
        print(f"{v:<14}{results['avg_recall'][v]:>9}")
    print(f"{'mempalace raw':<14}{0.929:>9}  (all cats/top-10, published)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
