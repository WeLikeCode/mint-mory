"""
MintMory performance benchmark — Momento baseline.

Gate: M7 — run after full search + dreaming are implemented.

Usage:
  python tests/benchmarks/momento_benchmark.py --count 10000 --db /tmp/bench.db

Targets (from ROADMAP.md §M7):
  - Hybrid search (FTS5 + vector) p95 < 100ms at 10k memories
  - add_memory p99 < 20ms
  - dream (light) on 10k memories < 60s
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter


def _seed_memories(store: StorageAdapter, count: int) -> list[str]:
    """Insert `count` random memories, return their IDs."""
    categories = [
        "fact",
        "skill",
        "preference",
        "identity",
        "context",
        "episodic",
        "temporal",
        "relationship",
    ]
    contents = [
        f"Memory {i}: the user {['likes', 'knows', 'prefers', 'believes'][i % 4]} thing {i}."
        for i in range(count)
    ]
    ids = []
    for i, content in enumerate(contents):
        r = store.add_memory(
            content=content,
            category=categories[i % len(categories)],
            source="agent",
        )
        ids.append(r.id)
    return ids


def run_benchmark(db_path: str, count: int) -> None:
    from mintmory.core.storage import StorageAdapter

    store = StorageAdapter(db_path)
    store.initialise()

    print(f"Seeding {count} memories…")
    t0 = time.perf_counter()
    _seed_memories(store, count)
    seed_ms = (time.perf_counter() - t0) * 1000
    print(f"  Seeding: {seed_ms:.0f}ms total ({seed_ms / count:.2f}ms each)")

    print("Benchmarking add_memory (100 samples)…")
    add_times = []
    for i in range(100):
        t0 = time.perf_counter()
        store.add_memory(content=f"Benchmark memory {i}", category="fact", source="agent")
        add_times.append((time.perf_counter() - t0) * 1000)
    p99_add = statistics.quantiles(add_times, n=100)[98]
    print(f"  add_memory: p99={p99_add:.2f}ms (target: <20ms)")

    print("Benchmarking hybrid search (50 queries)…")
    queries = ["user preference", "skill python", "context meeting", "fact climate", "memory thing"]
    search_times = []
    for i in range(50):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        store.search(q, limit=10)
        search_times.append((time.perf_counter() - t0) * 1000)
    p95_search = statistics.quantiles(search_times, n=100)[94]
    print(f"  search: p95={p95_search:.2f}ms (target: <100ms)")

    print("Benchmarking dream (light)…")
    t0 = time.perf_counter()
    store.dream(intensity="light")
    dream_ms = (time.perf_counter() - t0) * 1000
    print(f"  dream (light): {dream_ms:.0f}ms (target: <60000ms)")

    print("\nGates:")
    gate_add = "PASS" if p99_add < 20 else "FAIL"
    gate_search = "PASS" if p95_search < 100 else "FAIL"
    gate_dream = "PASS" if dream_ms < 60000 else "FAIL"
    print(f"  add_memory p99 < 20ms:         {gate_add}")
    print(f"  search p95 < 100ms:            {gate_search}")
    print(f"  dream < 60s:                   {gate_dream}")

    if "FAIL" in [gate_add, gate_search, gate_dream]:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000, help="Number of seed memories")
    parser.add_argument("--db", default="/tmp/mintmory_bench.db", help="DB path")
    args = parser.parse_args()
    run_benchmark(args.db, args.count)
