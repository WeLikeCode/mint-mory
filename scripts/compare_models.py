"""
LLM model comparison for MintMory (docs/OBSERVABILITY.md §2 / EXPERIMENTS.md §6.6).

Compares chat models (e.g. gemma4:e4b-it-qat vs qwen3.5:9b-nvfp4) on the two LLM
jobs MintMory actually does, against a built corpus DB:

  (a) L3 summaries   — quality via a deterministic rubric (fraction of distinctive
                       source tokens — digits / ALL-CAPS / quoted spans — preserved
                       in the summary) + per-call latency.
  (b) contradiction  — correctness vs docs/eval/contradiction_key.json (does the
      resolution         resolver archive the OUTDATED memory?) + latency.

Reads an existing DB (does NOT rebuild; build one first with seed_corpus.py).
Writes a JSON artifact and prints a table; paste the verdict into EXPERIMENTS.md §6.6.

  MINTMORY_LLM_PROVIDER=ollama uv run python scripts/seed_corpus.py --db /tmp/mintmory_corpus.db
  uv run python scripts/compare_models.py --db /tmp/mintmory_corpus.db \
      --models gemma4:e4b-it-qat,qwen3.5:9b-nvfp4 --sample 6 --out /tmp/model_compare.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

from mintmory.core.config import LLMProvider, LLMSettings
from mintmory.core.llm import LLMClient, build_conflict_resolver
from mintmory.core.prompts import SUMMARY_PROMPT
from mintmory.core.storage import StorageAdapter

_DISTINCTIVE = re.compile(r"\b\d[\d.,:/-]*\b|\b[A-Z]{2,}\b|\"[^\"]{2,40}\"")
NOISE = {"all", "api", "backend", "ing", "space"}


def _distinctive_tokens(text: str) -> set[str]:
    return {m.group(0).strip('"').lower() for m in _DISTINCTIVE.finditer(text)}


def _top_concepts(store: StorageAdapter, n: int, min_mem: int) -> list[tuple[str, list[str]]]:
    """Return up to n (entity, [contents]) for entities in >= min_mem active memories."""
    conn = store.connect()
    rows = conn.execute(
        "SELECT entity_ids, content FROM memories WHERE is_active=1 AND is_archived=0"
    ).fetchall()
    by_entity: dict[str, list[str]] = {}
    for entity_ids, content in rows:
        for ent in json.loads(entity_ids):
            if ent in NOISE:
                continue
            by_entity.setdefault(ent, []).append(content)
    ranked = sorted(
        ((e, c) for e, c in by_entity.items() if len(c) >= min_mem),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    return ranked[:n]


def _percentiles(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"p50": 0.0, "p95": 0.0}
    s = sorted(xs)
    return {
        "p50": round(s[len(s) // 2], 1),
        "p95": round(s[min(len(s) - 1, int(0.95 * len(s)))], 1),
    }


def eval_summaries(client: LLMClient, concepts: list[tuple[str, list[str]]]) -> dict[str, Any]:
    coverages: list[float] = []
    latencies: list[float] = []
    for concept, contents in concepts:
        source_tokens = (
            set().union(*(_distinctive_tokens(c) for c in contents)) if contents else set()
        )
        prompt = SUMMARY_PROMPT.format(
            concept=concept, notes="\n".join(f"- {c}" for c in contents[:20])
        )
        t0 = time.perf_counter()
        summary = client.chat(prompt)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        got = _distinctive_tokens(summary)
        if source_tokens:
            coverages.append(len(got & source_tokens) / len(source_tokens))
    return {
        "concepts": len(concepts),
        "coverage_mean": round(statistics.mean(coverages), 3) if coverages else None,
        "latency_ms": _percentiles(latencies),
    }


def _find_id(store: StorageAdapter, substring: str) -> str | None:
    row = (
        store.connect()
        .execute(
            "SELECT id FROM memories WHERE lower(content) LIKE ? LIMIT 1",
            (f"%{substring.lower()}%",),
        )
        .fetchone()
    )
    return row[0] if row else None


def eval_contradictions(
    db: str, settings: LLMSettings, conflicts: list[dict[str, Any]]
) -> dict[str, Any]:
    correct = wrong = abstain = missing = 0
    latencies: list[float] = []
    for conflict in conflicts:
        # Work on a throwaway copy so the shared corpus DB is never mutated.
        tmp = db + ".cmp"
        for suffix in ("", "-wal", "-shm"):
            Path(tmp + suffix).unlink(missing_ok=True)
        shutil.copyfile(db, tmp)
        store = StorageAdapter(tmp)
        outdated = _find_id(store, conflict["outdated_substring"])
        auth = _find_id(store, conflict["authoritative_substring"])
        if not outdated or not auth:
            missing += 1
            store.close()
            continue
        store.update_memory(auth, flagged_for_review=True, contradicts_ids=[outdated])
        store.update_memory(outdated, flagged_for_review=True, contradicts_ids=[auth])
        resolver = build_conflict_resolver(settings, store)
        assert resolver is not None
        record = store.get_memory(auth)
        assert record is not None
        t0 = time.perf_counter()
        actions = resolver(record)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        store.close()
        kill = [a for a in actions if a.action in ("DELETE", "UPDATE")]
        if not kill:
            abstain += 1
        elif any(a.target_id == outdated for a in kill):
            correct += 1
        else:
            wrong += 1
    total = correct + wrong + abstain
    return {
        "correct": correct,
        "wrong": wrong,
        "abstain": abstain,
        "missing": missing,
        "accuracy": round(correct / total, 2) if total else None,
        "latency_ms": _percentiles(latencies),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare LLM models for MintMory")
    parser.add_argument("--db", default="/tmp/mintmory_corpus.db")
    parser.add_argument("--models", default="gemma4:e4b-it-qat,qwen3.5:9b-nvfp4")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--sample", type=int, default=6)
    parser.add_argument("--contradiction-key", default="docs/eval/contradiction_key.json")
    parser.add_argument("--out", default="/tmp/model_compare.json")
    args = parser.parse_args()

    store = StorageAdapter(args.db)
    concepts = _top_concepts(store, args.sample, min_mem=3)
    store.close()
    conflicts = json.loads(Path(args.contradiction_key).read_text())["conflicts"]
    print(f"Sample: {len(concepts)} concepts, {len(conflicts)} contradiction conflicts\n")

    results: dict[str, Any] = {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        settings = LLMSettings(provider=LLMProvider.OLLAMA, model=model, base_url=args.base_url)
        client = LLMClient(settings)
        if not client.ping():
            print(f"!! {model}: endpoint not reachable, skipping")
            results[model] = {"error": "unreachable"}
            Path(args.out).write_text(json.dumps(results, indent=2))
            continue
        print(f"== {model} ==")
        try:
            summ = eval_summaries(client, concepts)
            print(f"  summary : coverage={summ['coverage_mean']} latency={summ['latency_ms']}")
            contra = eval_contradictions(args.db, settings, conflicts)
            print(
                f"  resolve : accuracy={contra['accuracy']} (correct={contra['correct']} "
                f"wrong={contra['wrong']} abstain={contra['abstain']}) "
                f"latency={contra['latency_ms']}"
            )
            results[model] = {"summary": summ, "contradiction": contra}
        except Exception as exc:  # noqa: BLE001 — record + continue so one model can't lose the others
            print(f"!! {model}: {type(exc).__name__}: {exc}")
            results[model] = {"error": f"{type(exc).__name__}: {exc}"}
        Path(args.out).write_text(json.dumps(results, indent=2))  # incremental: persist per model
    print(f"\nWrote {args.out}")
    print("JSON:", json.dumps(results))


if __name__ == "__main__":
    main()
