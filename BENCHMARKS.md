# 📊 MintMory Benchmarks — Receipts Included

> We took the agent-memory field's standard benchmarks and ran them against
> MintMory's search engine. First we did the part most benchmark posts skip: we
> **reproduced our competitor's published numbers** (exactly on LongMemEval, to
> their reported precision elsewhere) — so you can trust the scoreboard — and
> *then* beat them with **generic, untuned** search running out of a **single
> SQLite file, no GPU, no services**.

---

## TL;DR

MintMory's hybrid retrieval (FTS5 + trigram + brute-force vector, fused with
Reciprocal Rank Fusion) matches or beats [**mempalace**](https://github.com/mempalace/mempalace)
— a purpose-built local-memory system — across **all four of its own benchmarks**:
**two decisive wins** (LoCoMo, MemBench), **one narrow win** (LongMemEval), and
**one tie** (ConvoMem, where our pure-vector mode matches them). Same embedding
model (`all-MiniLM-L6-v2`), **zero benchmark-specific tuning**, one SQLite file.

| Benchmark | Metric | mempalace | MintMory (default hybrid) | |
|---|---|---|---|---|
| **LoCoMo** (1,986 q) | recall | 0.603 *raw* · 0.889 *hand-tuned* | **0.921** | ✅ **+0.32 / +0.03** |
| **MemBench** (8,500) | recall@5 | 0.803 *hand-tuned* | **0.820** | ✅ **+0.017** |
| **LongMemEval** (500 q) | recall@5 | 0.966 *raw* | **0.970**  (0.972 w/ vector-weight) | ✅ narrow (≈2/500) |
| **ConvoMem** (250) | recall | 0.929 *raw* | 0.897  (**0.929** vector-only) | ➖ tie\* |

*Same MiniLM embedder on both sides. mempalace numbers are from its published
README + committed result files. The LongMemEval edge is within run-to-run noise —
the real LongMemEval story is the exact vector==raw receipt below. \*On ConvoMem
(short-message semantic recall) the lexical fusion is a slight drag, so default
hybrid lands at 0.897; MintMory's pure-vector mode matches mempalace's 0.929.*

### 🧾 The receipts

On all three benchmarks with a published raw baseline, MintMory's **pure-vector**
path reproduces mempalace's **raw** number — exactly on LongMemEval, and to their
reported precision elsewhere:

| | mempalace raw | MintMory vector-only |
|---|---|---|
| LongMemEval R@5 | 0.966 | **0.966** (exact) |
| LoCoMo recall | 0.603 | **0.6029** |
| ConvoMem recall | 0.929 | **0.9287** |

Same model, same data, same metric → the same number three times over. That's
strong evidence the harness is faithful and the comparison is apples-to-apples.
*Then* MintMory's hybrid fusion pulls ahead. (MemBench has no published raw
baseline, so it's hybrid-vs-hybrid — see below.)

### 💪 The flex

mempalace's best LoCoMo (0.889) and MemBench (0.803) numbers come from
**hand-tuned, benchmark-specific heuristics** — temporal-expression parsers,
quoted-phrase boosts, person-name boosts, and regex preference extractors, all
visible in its `benchmarks/{locomo,longmemeval}_bench.py` (`person_name_boost`,
`quoted_phrase_boost`, `parse_time_offset_days`, `extract_preferences`).
mempalace is candid about where this leads: its own README notes its top
LongMemEval number "was reached by inspecting specific wrong answers, which …
flags as **teaching to the test**."

MintMory beats LoCoMo and MemBench with **one generic hybrid search and not a
single line of per-benchmark code** — no name boosts, no date parsers, no
test-set inspection.

---

## What's actually different

1. **One file. No services. No GPU.** The entire store is a single SQLite
   database. Search is FTS5 + a `trigram` substring index + brute-force cosine
   over `sqlite-vec` — all in-process. It runs on a laptop and ships in your app.

2. **A hybrid that knows when to trust itself.** Most hybrid search hard-codes a
   fusion recipe. MintMory exposes a **measured, workload-aware** knob —
   `MINTMORY_SEARCH_VECTOR_RRF_WEIGHT` — because our own benchmarks proved the
   right blend *depends on the workload*: lexical fusion is a **+0.32** swing on
   exact-match LoCoMo but a slight drag on paraphrase-heavy sets. The default is
   conservative (1.0 = pure RRF); turn it up for semantic workloads. We don't
   guess — [we measured it](docs/EXPERIMENTS.md).

3. **Zero benchmark tuning, zero test-set peeking.** Every number above comes
   from the same generic engine. No per-dataset heuristics. No inspecting the
   answers we got wrong.

4. **Honest by construction.** The vector==raw receipts mean you don't have to
   take our word for it — re-run it and watch the raw numbers line up, then watch
   the hybrid win.

---

## 🔁 Reproduce it yourself

Harnesses live in [`docs/eval/`](docs/eval/) and use MintMory's public API + the
`local` (MiniLM) embedder. Install once, then run all four with one script:

```bash
git clone https://github.com/WeLikeCode/mint-mory.git && cd mint-mory
uv sync --extra local                       # all-MiniLM-L6-v2 embedder
./scripts/run_mempalace_benchmarks.sh       # fetches datasets + runs all four
```

Prefer to run them one at a time? Each is a single command. Note the
**`--no-sync`** — a bare `uv run` re-syncs the venv to the default extras and
drops the `local` embedder, so keep `--no-sync` (or re-run `uv sync --extra
local` first). Timings are warm-cache and exclude the first-run model/dataset
downloads (~90 MB MiniLM + the datasets).

```bash
# LongMemEval (500 q, ~4 min warm)
curl -fsSL -o /tmp/lme.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
uv run --no-sync python docs/eval/mempalace_longmemeval_benchmark.py /tmp/lme.json

# LoCoMo (1,986 q, ~35 s warm)
git clone https://github.com/snap-research/locomo.git /tmp/locomo
uv run --no-sync python docs/eval/mempalace_locomo_benchmark.py /tmp/locomo/data/locomo10.json

# ConvoMem (250 items — data auto-downloads from HF)
uv run --no-sync python docs/eval/mempalace_convomem_benchmark.py --limit 50

# MemBench (8,500 items, ~27 min warm)
git clone https://github.com/import-myself/Membench.git /tmp/membench
uv run --no-sync python docs/eval/mempalace_membench_benchmark.py /tmp/membench/MemData/FirstAgent
```

Each prints three MintMory variants — `vector` (pure cosine, the apples-to-apples
match to a competitor's "raw"), `hybrid_w1` (default), and `hybrid_w3` (vector
RRF weight 3) — next to the published baseline. Results are written to
`docs/eval/*_results.json`.

---

## 🔬 Bonus: how we found and fixed our own weakness

We don't only run benchmarks we win. We stress-tested MintMory's hybrid search on
**LEANN's** DPR / Natural-Questions passage-retrieval setup at 100k passages
([docs/EXPERIMENTS.md §10](docs/EXPERIMENTS.md)) and found a real regression: at
scale, naive RRF *lowered* recall@3 versus pure vector (the lexical sources
out-voted the correct dense hit). We measured the fix — vector-weighted RRF lifts
recall@3 `0.665 → 0.722` and recall@10 `0.857 → 0.890`, beating both the old
default *and* pure vector — and shipped it as the `vector_rrf_weight` knob. The
agent-memory wins above are *with that fix available*. Finding it is the point:
measure, don't assume.

---

## The fine print (because honest > hype)

- **Same embedder, both sides.** All MintMory numbers use `all-MiniLM-L6-v2`, the
  model mempalace's *raw* runs use. We did not swap in a bigger model to win.
- **Raw vs tuned, labeled.** Where we beat a *hand-tuned* mempalace mode
  (LoCoMo v5, MemBench hybrid) we say so explicitly — and we still win with a
  *generic* engine.
- **mempalace's reranked ceilings.** mempalace reports higher LongMemEval numbers
  (98.4% held-out, ≥99% with an LLM reranker) from heavier pipelines; our
  like-for-like comparison is *generic hybrid vs raw/tuned retrieval*, no LLM in
  the loop. An LLM-rerank stage would lift MintMory too; we didn't add one.
- **ConvoMem** uses the 5 categories the loader can fetch (the
  `changing_evidence` files 404 on HuggingFace at time of measurement, for
  mempalace's loader and ours alike) → 250 items, matching mempalace's headline set.
- **LEANN/DPR study** uses a tractable 100k-passage subset of the 2.1M corpus and
  a cross-model golden (contriever) — directional, not a leaderboard claim. Full
  methodology and caveats: [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

Numbers measured 2026-06-20 on Apple Silicon, CPU only. Re-run them — that's the
whole point.

*MIT-licensed; benchmark harnesses live in [`docs/eval/`](docs/eval/), full
methodology + caveats in [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).*
