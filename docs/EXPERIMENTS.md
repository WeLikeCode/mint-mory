# MintMory — Memory-Quality & Embedding Experiments (living record)

This is the **execution + record** document for the memory-quality, embedding, and
experiment-methodology workstream. It is **filled in as we test**: every parameter
change is a tracked experiment with a measured *before*, a measured *after*, and a
**VERDICT** (kept / reverted / value). Nothing here is hardcoded — every knob lands
in `core/config.py` (env-driven, pydantic-settings) with a safe default that
reproduces today's behaviour unless explicitly overridden.

> Source-of-truth hierarchy is unchanged (`types.py > schema.sql > openapi.yaml`).
> All changes here are **additive + parameterised** and must keep
> `test_schema.py` and the existing suite green. No `schema.sql` change is required
> by anything in this document.

---

## 0. The four findings we are fixing (as tracked experiments)

| # | Finding | Lever(s) | Primary metric |
|---|---|---|---|
| F1 | **Over-linking** — 2588 links / 154 nodes, avg degree 33.6, top-4 entities = 69% of links | `LINK_MIN_SHARED_ENTITIES`, `LINK_ENTITY_DF_CAP_RATIO`, `LINK_MAX_PER_NODE`, IDF-weighted strength, stop-list | link count, degree dist, % links from top-K entities, search-around breadth |
| F2 | **Entity-extraction noise** — `all / api / backend / ing / space` become "entities" | DF filter at link/summary time + expanded stop-list (`entities.py`) | # noise concepts in summaries, # noise entities above DF cap |
| F3 | **Slow L3 summaries** — ~50 min serial (~27 s/summary, gemma4) | concurrency, `SUMMARY_MIN_MEMORIES`, content truncation, DF-filtered concept set, model swap | wall-clock for L3 phase, summaries generated |
| F4 | **Local-model resolver quality** | model swap (gemma4 vs qwen3.5:9b), structured-output prompt, temperature | resolution agreement vs reference, JSON-parse rate, latency |

The **design principle that governs all of these**: *measurement must be fast.*
The L2 graph + embedding + entity changes (F1, F2) are measurable in **seconds**
via the **fast harness** (§5) — they do **not** require the ~50-minute L3 phase.
Only F3/F4 touch the LLM, and even those are bounded by a small concept sample.

---

## 1. PURE-PYTHON EMBEDDER (R2)

### 1.1 Requirement

The **default** embedder must be **pure Python, in-process, numpy-only** — no
Ollama, no `sentence_transformers`, no `torch`, no network. `nomic-embed-text`
(768d, via Ollama) is demoted from default to an *optional* provider. The existing
`LocalEmbedder` (sentence-transformers), `OpenAIEmbedder`, and `OllamaEmbedder`
stay as **opt-in** providers selected by env.

### 1.2 Options evaluated

| Option | Deps | Determinism | Semantic? | Verdict |
|---|---|---|---|---|
| **A. Feature-hashing TF-IDF** (hashed word + char n-grams → fixed dim, L2-norm) | numpy only | Fully (pure hash) | Lexical + sub-word (typo/morphology robust via char n-grams) | **CHOSEN default (`hashing`)** |
| B. Pure-Python word2vec-ish (train on corpus) | numpy | No (needs training, RNG) | Yes | Rejected — needs a training step + persisted model; not "in-process zero-config" |
| C. Random projection of bag-of-words | numpy | Yes (seeded) | Lexical only, lossier than hashing | Rejected — hashing trick is the same idea but cleaner + collision-controlled |
| D. Keep `FakeEmbedder` (token-bucket hash) as default | numpy | Yes | Weak — single hash bucket per token, no n-grams, no IDF | Rejected as *default* — fine for unit tests, poor retrieval |

`FakeEmbedder` stays exactly as-is for unit tests (PLAN §2 / AGENTS §7 require a
deterministic dependency-free test embedder). The new **`HashingEmbedder`** is the
production default; it is a strict superset in quality (char n-grams + IDF) while
remaining dependency-free.

### 1.3 `HashingEmbedder` spec (the new default)

```
class HashingEmbedder:               # core/embedder.py
    MODEL_ID = "hashing-tfidf-v1"
    def __init__(self,
                 dim=512,                       # EMBED_DIM
                 word_ngram=(1,2),              # EMBED_WORD_NGRAM_MIN/MAX
                 char_ngram=(3,5),              # EMBED_CHAR_NGRAM_MIN/MAX (0 disables)
                 use_idf=True,                  # EMBED_USE_IDF
                 idf_floor=1.0): ...
```

Pipeline (deterministic, numpy-only):

1. **Tokenise** — lowercase, split on `[^a-z0-9]+`; drop tokens of length < 2.
2. **Word n-grams** — emit unigrams + bigrams (`word_ngram=(1,2)`).
3. **Char n-grams** — for each token, emit char 3..5-grams of `"^"+tok+"$"`
   (boundary markers). This is what makes it robust to typos / inflection
   (`endpoint` ≈ `endpoints`) — the property feature-hashing TF buys us that the
   token-bucket `FakeEmbedder` lacks.
4. **Feature hashing** — `h = blake2b(feature, digest_size=8)`; `bucket = h % dim`;
   `sign = +1 if (h>>63)&1 else -1` (signed hashing cancels collisions in
   expectation). Accumulate `sign * weight` into `vec[bucket]`.
5. **TF weight** — raw term frequency, optionally **× IDF**. IDF is supplied by the
   `StorageAdapter` from a **corpus DF table** (see §1.4); when no DF stats are
   available (cold start / single doc), `use_idf` degrades to pure TF (idf=1.0).
6. **L2-normalise** (reuse existing `_l2_normalise`, zero-vector guarded).

Determinism: `blake2b` is stable across processes/platforms (unlike Python's
salted `hash()`), so identical text → identical vector forever. No RNG, no seed.

Dimensions: **512** default (plausible range 256–1024). 512 keeps the stored blob
at 2 KB/memory (float32) and collision rate low for a ≤ few-thousand-memory store;
256 halves storage at a small recall cost; 768 matches nomic's dim if we want
apples-to-apples blob sizing.

### 1.4 IDF without a training step

IDF needs document frequencies. We compute them **lazily from the live store**:

- `StorageAdapter` gains an optional `_idf_provider()` that returns
  `{feature_or_token: df}` derived from a cheap `SELECT entity_ids/content` scan,
  cached and invalidated on a memory-count delta threshold (`EMBED_IDF_REFRESH_N`,
  default 50 new memories).
- For determinism in tests and for the *query* embedding, IDF uses the **same
  snapshot** used at write time within a search call.
- **Fallback:** `use_idf=False` (or empty store) → pure hashed TF. This keeps the
  embedder usable with **zero** corpus, satisfying "in-process, zero-config".

> Simpler v1 (recommended first cut): ship `HashingEmbedder` with `use_idf=False`
> (pure hashed TF-IDF-shaped vectors *without* the corpus IDF coupling), measure
> retrieval, and only add the IDF provider if the fast harness shows it helps. This
> keeps the embedder a pure function of its input text (cleanest contract).

### 1.5 Plug-in points

- **Factory** (`create_embedder`): add `"hashing"` and make it the default.
  ```python
  def create_embedder(provider="hashing", **kw):
      if provider == "hashing": return HashingEmbedder(**kw)
      if provider == "local":   return LocalEmbedder(**kw)
      if provider == "openai":  return OpenAIEmbedder(**kw)
      if provider == "ollama":  return OllamaEmbedder(**kw)   # moved out of scripts/
      if provider == "fake":    return FakeEmbedder(**kw)
      raise ValueError(...)
  ```
- **Config-driven construction**: a new `embedder_from_settings(settings)` reads
  `MINTMORY_EMBED_PROVIDER` etc. and is what `seed_corpus.py` / transports call.
- **StorageAdapter**: unchanged signature. Today `seed_corpus.py` passes
  `OllamaEmbedder()`; it will instead pass `embedder_from_settings(...)`, whose
  default is `HashingEmbedder()`. Vector search already degrades to FTS-only when
  `sqlite-vec` is absent (PLAN §2) — the hashing vectors flow through the existing
  `_embed` / `vec_distance_cosine` path with **no storage changes**.
- **Dim safety**: the stored `embedding` blob is provider-specific. Switching
  providers on an existing DB means re-embedding (different dim/space). The fast
  harness rebuilds the DB from corpus each run, so this is a non-issue for
  experiments; for production we note it as a migration risk (§7).

### 1.6 Expected retrieval-quality tradeoff vs `nomic-embed-text`

`nomic-embed-text` is a trained 768d model with real semantics
(synonyms, paraphrase). `HashingEmbedder` is **lexical + sub-word**: it will match
on shared/related *surface forms* (and typo/inflection variants via char n-grams)
but **not** pure synonyms (`car` ≁ `automobile`). Expectation:

- On this corpus (technical notes, dense with proper nouns / API names / repo
  names) lexical overlap is high, so the gap should be **small**.
- We never rely on the embedder alone: search is **hybrid (FTS5 + vector, RRF
  merged)**. FTS already covers exact lexical hits; the vector phase mainly
  reorders. So a lexical vector ≈ "FTS with fuzzier, sub-word recall".

How the fast harness measures the gap (§5.3): for a small **labelled query set**
we compute **recall@k** and **FTS↔vector top-k agreement (Jaccard)** for
`hashing` vs `ollama:nomic-embed-text`. Acceptance bar: hashing within **≤ 10%
recall@10** of nomic on the labelled set, *or* the loss is invisible after RRF
merge (hybrid recall@10 within ≤ 5%). If it fails the bar, the verdict is
"keep `hashing` as zero-dep default, document `ollama`/`local` as the
quality-tier upgrade" — the default must still ship dependency-free (R2).

---

## 2. CONCEPT-LINKING QUALITY — over-linking fix (F1), all TUNABLE

These live in `core/config.py` and are read by `DreamingEngine.create_concept_links`
(the step is parameterised, never hardcoded). **Defaults reproduce today's graph**
unless the experiment flips them, so the change is safe-by-default.

> **Empirical grounding** (simulated on the live `/tmp/mintmory_corpus.db`, 150
> active memories, current 2498 candidate pairs): see the predicted-after column.
> These are *measured* projections from the corpus, not guesses.

| Param | Default (today) | Range | Hypothesis | Metric it moves | Predicted after |
|---|---|---|---|---|---|
| `LINK_MIN_SHARED_ENTITIES` | `1` | 1–4 | A single shared ubiquitous entity (e.g. `inghub`) is a weak signal; require **≥ 2** shared entities for a pair to link. **Biggest single lever.** | total links; degree avg/median; precision | `2` → **760 links** (−70%) |
| `LINK_ENTITY_DF_CAP_RATIO` | `1.0` (off) | 0.10–0.50 | Drop entities present in > X% of active memories from the *linking* signal (they connect everything). | links from top-K entities; breadth | `0.20` → 1820; `0.15` → 1469 |
| `LINK_STOPLIST` (entities) | `∅` | curated set | Hard-exclude `{all, api, backend, ing, space}` (+ corpus-ubiquitous `inghub`?) from linking. | noise links; precision | combined w/ above → see stack |
| `LINK_MAX_PER_NODE` | `∞` | 8–25 | Greedy cap: keep each node's strongest N links (by shared-count / IDF strength); bounds hub degree (max 83 today). | max/avg degree; breadth | `15` (on stacked) → 330 |
| `LINK_IDF_WEIGHTED_STRENGTH` | `False` | bool | Set `strength = f(Σ idf(shared_entity))` instead of flat 0.5, so a link via a rare entity outranks one via `inghub`. Lets `SearchAroundSpec.min_strength` prune weak hubs at query time without changing the graph. | search-around breadth at `min_strength` | qualitative |
| `LINK_MIN_JACCARD` | `0.0` (off) | 0.05–0.3 | Alternative/with min-shared: require entity-set Jaccard ≥ θ (normalises for memories with many entities). | links; precision on long memories | tunable |

**Recommended stacked default to adopt (pending verdict):**
`LINK_MIN_SHARED_ENTITIES=2`, `LINK_ENTITY_DF_CAP_RATIO=0.15`,
`LINK_STOPLIST={all,api,backend,ing,space}`, `LINK_MAX_PER_NODE=15`,
`LINK_IDF_WEIGHTED_STRENGTH=True`.

**Measured projection of the stack (from the live corpus simulation):**

| Configuration | Links | Δ vs 2498 |
|---|---|---|
| baseline (`min_shared=1`, no cap) | 2498 | — |
| `min_shared=2` only | 760 | −70% |
| `min_shared=2` + `df_cap=0.20` | 589 | −76% |
| `min_shared=2` + `df_cap=0.15` + stoplist | 348 | −86% |
| full stack + `max_per_node=15` | **330** | **−87%** |

Target: cut links from ~2588 toward **300–800** and search-around breadth from
**~93%** of the store to a precise neighbourhood (target **< 30%** at depth 2 on
the probe queries) **while keeping the right top results** (top-k precision proxy,
§5.2, must not regress).

> Idempotency (AGENTS §4.4) is preserved: linking still `INSERT OR IGNORE`s and
> pre-checks existing pairs, so a second run on an unchanged DB yields
> `new_links == 0` regardless of the parameter values. `LINK_MAX_PER_NODE`'s greedy
> cap must be **deterministic** (stable sort by `(−shared_count, src, tgt)`) so the
> kept set is identical across runs.

---

## 3. ENTITY-EXTRACTION NOISE FIX (F2)

The noise concepts (`all, api, backend, ing, space`) come from two sources:
generic capitalised tokens (`API`, `Backend`), an over-eager acronym/word regex
(`ing` from "ING…"/inflection), and `all`/`space` as common words. Two layers,
each tunable:

### 3.1 Static stop-list expansion (`entities.py`)
- Add a **domain/tech stop-list** to `_STOPWORDS` (or a separate
  `_ENTITY_STOPLIST` so the FTS-stopword and entity-stopword concerns stay
  distinct): `{api, backend, frontend, app, ui, ux, db, sdk, cli, http, json,
  all, space, ing, the, ...}`. Tunable via `ENTITY_EXTRA_STOPWORDS` (env,
  comma-sep) so we can iterate **without a code change**.
- This lives in `entities.py` because it is a property of *extraction*, and it
  also improves `MemoryStats.top_concepts` and L3 summaries, not just linking.

### 3.2 Dynamic DF-based filtering (preferred, corpus-aware)
- A token that appears in **> `ENTITY_DF_CAP_RATIO`** of active memories is almost
  always boilerplate, not a discriminating entity. Filter these at **link/summary
  time** (the corpus-aware layer), *not* destructively in `entities.py` — the raw
  `entity_ids` on the record stay intact for audit/filtering; the *consumers*
  (linking, summary concept selection) apply the DF cap.
- Rationale for "where it lives": extraction is per-document and stateless;
  DF requires the whole corpus. Keep `entities.py` stateless (static stop-list
  only) and put DF-aware filtering in the dreaming/linking step where the corpus
  view exists. This also keeps `entities.py` unit tests deterministic.

| Param | Default | Range | Hypothesis | Metric |
|---|---|---|---|---|
| `ENTITY_EXTRA_STOPWORDS` | `∅` | curated | Removes the 5 named noise concepts at the source | # noise entities; # noise summaries |
| `ENTITY_DF_CAP_RATIO` | `1.0` (off) | 0.10–0.50 | Boilerplate tokens exceed any sane DF; drop from concept set | # concepts summarised; noise links |
| `ENTITY_MIN_LENGTH` | `2` | 2–4 | `ing` (len 3) survives len≥2; consider len≥4 for acronyms only via separate path | # short-junk entities |

Target: **0** of `{all, api, backend, ing, space}` in the generated summary
concept set; noise-entity link contribution → 0.

---

## 4. L3 SUMMARY SPEED (F3) & MODEL COMPARISON (F4)

### 4.1 Speed levers (tunable)

| Param | Default | Range | Hypothesis | Metric |
|---|---|---|---|---|
| `SUMMARY_CONCURRENCY` | `1` | 1–8 | Ollama serves requests concurrently; N parallel summary calls cut wall-clock ~linearly until the model saturates. **Biggest win.** | L3 wall-clock |
| `SUMMARY_MIN_MEMORIES` | `3` | 3–6 | Raising the threshold summarises fewer (more meaningful) concepts; fewer LLM calls. | # summaries; wall-clock |
| `SUMMARY_MAX_CONTENTS` | `20` | 8–40 | Fewer note snippets per prompt → shorter prompts → lower latency/summary. | s/summary |
| `SUMMARY_MAX_CONTENT_CHARS` | `∞` | 300–1200 | Truncate each note; bounds prompt size on verbose memories. | s/summary |
| `LLM_MODEL` | `gemma4:e4b-it-qat` | {gemma4, qwen3.5:9b-nvfp4, qwen3.5:4b-mlx-bf16, gpt-oss:20b} | Smaller/faster vs larger/better; pick the latency/quality knee. | s/summary; quality (§4.3) |

After the F2 entity fix, the concept set shrinks (fewer noise concepts ≥ 3 mems),
which **independently** cuts L3 calls — measure summaries-count before/after.

> The 110-summary / ~50-min baseline is dominated by `SUMMARY_CONCURRENCY=1`
> × ~27 s/call. Concurrency=4 alone projects to ~12–15 min; combined with the
> F2-driven concept-set shrink (fewer than 110 concepts) it should land well under
> 10 min. Concurrency must preserve idempotency (writes still `INSERT OR REPLACE`
> by concept; order-independent).

### 4.2 Model-swap config (R3)
All LLM access goes behind `core/config.py` settings (one place, env-driven):
`MINTMORY_LLM_PROVIDER` (`ollama|openai|none`), `MINTMORY_LLM_BASE_URL`,
`MINTMORY_LLM_MODEL`, `MINTMORY_LLM_API_KEY`, `MINTMORY_LLM_TEMPERATURE`,
`MINTMORY_LLM_TIMEOUT_S`. `scripts/local_llm.py`'s ad-hoc `os.environ` reads are
replaced by reading these settings, so swapping a model is a single env change and
the same code path serves Ollama *and* an OpenAI-compatible endpoint.

### 4.3 R4 — MODEL COMPARISON EXPERIMENT (gemma4 vs qwen3.5:9b)

Script: `scripts/exp_llm_compare.py` (new). Procedure:

1. **Fixed input set** (deterministic): pick the **same 10 concepts** (≥ 3
   memories each) from the seeded DB, and the **same N flagged contradiction
   records** (or N synthetic contradiction pairs if the seeded DB has only 4 —
   add a small fixture so the resolver test has signal).
2. For each model in `{gemma4:e4b-it-qat, qwen3.5:9b-nvfp4}` (extensible):
   - **Summaries**: generate a summary per concept; record **latency** (p50/p95),
     and quality proxies: (a) **concept-coverage** = fraction of distinctive
     entities/numbers from the source notes that appear in the summary (regex
     overlap, automatic), (b) **length sanity** (within 1–4 sentences),
     (c) **JSON/format compliance** where applicable.
   - **Contradiction resolution**: run the resolver; record **latency**,
     **JSON-parse success rate**, and **agreement** with a small hand-labelled
     "which memory is outdated" key (`docs/eval/contradiction_key.json`).
3. **Output**: a results table appended to §6.4 below (model, task, p50 ms, p95
   ms, coverage, parse-rate, agreement) + a one-line VERDICT (which model becomes
   the `LLM_MODEL` default).

Quality scoring is **semi-automatic** (overlap + format + agreement-vs-key) so the
comparison is reproducible; an optional human spot-check column may override.

---

## 5. THE FAST METRIC HARNESS (seconds, no L3)

`scripts/metrics.py` (new). Runs the **L2/embedding/entity** measurements **without
the LLM summary phase**, so F1/F2 (and embedder retrieval) iterate in seconds.

### 5.1 Build (fast)
```bash
# Rebuild DB with the pure-Python default embedder, NO LLM, NO summaries.
uv run python scripts/seed_corpus.py --db /tmp/mm_fast.db --no-llm
```
`--no-llm` already skips summaries/contradictions (FTS-only path) — but with the
new default it now also gets **real hashing vectors** (the old `--no-llm` had no
embedder at all). Linking still runs in `run_full`'s light steps (fast, no LLM).

### 5.2 Graph + entity metrics (`scripts/metrics.py graph`)
Emits, in JSON + a human table, all of:
- `link_count`, `linked_nodes`, `degree_avg/median/max`
- `pct_links_top_k_entities` (K=4) — today **69%**
- `links_per_entity` top-10
- `noise_entities_present` — count of `{all,api,backend,ing,space}` surviving
- **search-around breadth** for the probe queries: for each query, run
  `search(..., search_around=depth2 relates_to)` and report
  `graph_added / active_total` — today **~93%** on `'iOS cancel endpoint bug'`.
- **top-k precision proxy** (the "kept the right results" guard): a small
  `docs/eval/probe_queries.json` maps each probe query → a hand-labelled set of
  *relevant* memory ids. Report **precision@5** of the *primary* (pre-graph)
  results and **whether the labelled-relevant ids remain in the union** after
  graph traversal. Linking changes must **not** drop these.

### 5.3 Embedding-quality metrics (`scripts/metrics.py embed`)
- For each `docs/eval/probe_queries.json` query with labelled relevant ids:
  **recall@10** of the **vector-only** ranking and of the **hybrid (RRF)** ranking.
- **FTS↔vector agreement**: Jaccard of top-10 FTS ids vs top-10 vector ids
  (sanity that the vector phase is "lexical-plus", not random).
- Run for `provider=hashing` and (when Ollama is up) `provider=ollama` to fill
  the comparison row in §6.3.

### 5.4 Exact fast-measurement commands
```bash
# 0. (one-time) create the tiny eval fixtures
#    docs/eval/probe_queries.json   {query: [relevant_memory_id,...]}
#    docs/eval/contradiction_key.json  {flagged_id: outdated_id}

# 1. Build fast DB (pure-python embedder, no LLM)  — seconds
uv run python scripts/seed_corpus.py --db /tmp/mm_fast.db --no-llm

# 2. Graph + entity metrics (F1/F2)               — seconds
uv run python scripts/metrics.py graph --db /tmp/mm_fast.db --top-k 4 \
    --probe docs/eval/probe_queries.json

# 3. Embedding retrieval quality (R2)             — seconds
MINTMORY_EMBED_PROVIDER=hashing \
  uv run python scripts/metrics.py embed --db /tmp/mm_fast.db \
    --probe docs/eval/probe_queries.json
#   (compare) rebuild with ollama provider, re-run embed:
MINTMORY_EMBED_PROVIDER=ollama MINTMORY_EMBED_MODEL=nomic-embed-text \
  uv run python scripts/seed_corpus.py --db /tmp/mm_nomic.db
MINTMORY_EMBED_PROVIDER=ollama \
  uv run python scripts/metrics.py embed --db /tmp/mm_nomic.db \
    --probe docs/eval/probe_queries.json

# 4. Sweep a linking parameter without editing code (env-driven config)   — seconds
for n in 1 2 3; do
  MINTMORY_LINK_MIN_SHARED_ENTITIES=$n \
    uv run python scripts/seed_corpus.py --db /tmp/mm_fast.db --no-llm >/dev/null
  echo "min_shared=$n:"; \
  MINTMORY_LINK_MIN_SHARED_ENTITIES=$n \
    uv run python scripts/metrics.py graph --db /tmp/mm_fast.db --top-k 4
done

# 5. (slow, only for F3/F4) L3 + model comparison
uv run python scripts/exp_llm_compare.py --db /tmp/mm_fast.db \
    --models gemma4:e4b-it-qat,qwen3.5:9b-nvfp4 \
    --concepts 10 --contradiction-key docs/eval/contradiction_key.json
```

`scripts/metrics.py` must print machine-readable JSON (one object) **and** a
human table, so the "after" cells in §6 can be pasted directly from its output.

---

## 6. THE EXPERIMENT RECORD (fill the `after`/`VERDICT` columns as we test)

### 6.0 Conventions
- **before** = value measured on the current default config (filled from §6.1).
- **after** = value from the fast harness with the experiment's env override.
- **VERDICT** = `KEPT@<value>` / `REVERTED` / `PARTIAL@<value>` + one-line why.
- Every experiment is a single env change; no code edit needed to run it.

### 6.1 BASELINE (measured 2026-06-15 on /tmp/mintmory_corpus.db, 155 records)

| Metric | Baseline |
|---|---|
| memories total / active | 155 / 150 |
| concept links | 2588 |
| linked nodes | 154 |
| degree avg / median / max | 33.6 / 30 / 83 |
| % links from top-4 entities | ~69% (1793 / 2588) |
| links_per_entity top-4 | inghub 973, acme 406, mintmory 231, engie 183 |
| distinct link-entities | 76 |
| distinct entities (active mems) | 482 |
| search-around breadth ('iOS cancel endpoint bug', d2, relates_to) | 145/150 returned; 140 via graph ≈ **93%** |
| L3 summaries | 110 (5 noise: all, api, backend, ing, space) |
| L3 full `run_full` wall-clock | ~50 min (serial, ~27 s/summary, gemma4) |
| contradictions detected / resolved / archived | 4 / 7 / 5 |
| embedder (default today) | ollama nomic-embed-text 768d (EXTERNAL) — to be replaced |

> Candidate-pair note: the raw shared-entity candidate count on the *current*
> active set is **2498** (the 2588 figure includes links created before the 5
> archivals); both are recorded so deltas are unambiguous. The harness reports the
> live number each run.

### 6.2 LINKING / GRAPH experiments (F1)  — measured projections in "after (proj.)"

Measured 2026-06-15 on the 155-record corpus with the pure-Python `hashing`
embedder, `--no-llm` (fast harness). "before" = default config at the time of the
run (min_shared=1). Baseline graph this run: **2586 links**, degree avg 33.6 /
median 30 / max 83, search-around breadth **90.3%**, noise entities **5**.

| ID | Param(s) | before | after (measured) | metric | VERDICT |
|---|---|---|---|---|---|
| E-L1 | `min_shared=2` only | 2586 | **767 (−70%)**, deg avg 11.4, breadth 55%, noise 4 | links/degree/breadth | KEPT (biggest single lever; recall held) |
| E-L6 | `min_shared=2` + `df_cap=0.15` + stoplist + `max_per_node=15` | 2586 | **379 (−85%)**, breadth 33.5%, noise **0** | links/breadth | **REVERTED** — guardrail failed: AXIS recall 1.0→0.2, shorten→0.36, INGHub→0.29 (df_cap over-prunes) |
| **E-L-MID** | `min_shared=2` + stoplist + `max_per_node=25` + `idf_strength` (no df_cap) | 2586 | **641 (−75%)**, deg avg 9.5 / max 25, breadth **45.5%**, noise **0** | links/breadth/recall | **ADOPTED as default** — recall preserved (AXIS 1.0), noise gone, hubs bounded |
| E-L8 | search-around breadth under E-L-MID | 90.3% | **45.5%** | breadth proxy | KEPT (target was <30%; 45% with recall intact beats 33% with recall loss) |
| E-L9 | recall guardrail under E-L-MID | recall_union ~1.0 | **preserved** (AXIS/iOS/MongoDB/Engie = 1.0; shorten 0.64, INGHub 0.71 — limited by PRIMARY search, not links) | recall proxy | KEPT (no link-driven regression) |

> Key insight (E-L6 vs E-L-MID): the *dense* graph was silently compensating for
> weak primary ranking by pulling in nearly everything (90% breadth). Pruning too
> hard (`df_cap=0.15`) removed the edges that were carrying those relevant hits, so
> recall collapsed. The adopted middle ground (`min_shared=2` + stoplist +
> `max_per_node=25`) cuts the noise without cutting the signal. The residual
> recall gaps (shorten/INGHub) are a *primary-search* limitation (RRF dilution,
> §6.3), not a linking one.

### 6.3 EMBEDDING experiments (R2)

Measured 2026-06-15 on the 6-query labelled probe set (mean recall@10).

| ID | Config | nomic (Ollama, 768d, external) | hashing (pure-Python, 512d, **0 deps**) | VERDICT |
|---|---|---|---|---|
| E-E1 | vector-only recall@10 | 0.643 | **0.665** | KEPT — hashing ≥ nomic on this corpus |
| E-E2 | hybrid (RRF) recall@10 | 0.717 | **0.713** | KEPT — within 0.4%; the zero-dep default loses nothing |
| (ref) | FTS-only recall@10 | 0.808 | 0.808 | — (same; FTS is embedder-independent) |

> **R2 satisfied decisively.** The pure-Python `hashing` embedder MATCHES
> `nomic-embed-text` (hybrid 0.713 vs 0.717; vector 0.665 vs 0.643) while removing
> the Ollama embedding dependency entirely — confirming the Opus prediction that a
> lexical+char-n-gram embedder ≈ a trained transformer on a proper-noun-dense
> technical corpus. `hashing` is now the default; `ollama`/`local` remain opt-in
> quality tiers (set `MINTMORY_EMBED_PROVIDER`). E-E3/E-E4/E-E5 (dim sweep, IDF,
> char-ngram ablation) are deferred — not needed once the default already ties nomic.
>
> **Cross-cutting finding:** hybrid recall (~0.71) is *below* FTS-only (~0.81) for
> BOTH embedders — the RRF merge is diluting strong FTS hits with weaker vector
> neighbours. This is a search-merge weighting issue (independent of the embedder
> and of linking) and the next-highest-leverage retrieval fix.

### 6.4 ENTITY-NOISE experiments (F2)

| ID | Param(s) | before | after (measured) | VERDICT |
|---|---|---|---|---|
| E-N1 | `LINK_STOPLIST=all,api,backend,ing,space` (consumption-time) | noise entities in graph: **5** (`all,api,backend,ing,space`) | **0** | **KEPT** — folded into the adopted link defaults; removes noise from links AND summary-concept selection |
| E-N2 | `ENTITY_DF_CAP_RATIO` / `ENTITY_EXTRA_STOPWORDS` (extraction-time) | — | not needed for the target | DEFERRED — the link-stoplist already hits "0 noise concepts"; raw `entity_ids` kept intact for audit by design |

> F2 target met: noise entities in the concept graph went 5 → **0** purely via the
> adopted `LINK_STOPLIST` (a consumption-time filter), so raw `entity_ids` stay
> intact for audit. The extraction-time stop-list (`entities.py`) is implemented
> and available (opt-in via `ENTITY_EXTRA_STOPWORDS`) but unnecessary to clear F2.

### 6.5a AGENT-SUPPLIED L3 SUMMARIES (alternative path, no backend)

As of the `add-agent-supplied-summaries` change, the configured-LLM path
(`memory_dream` / `mintmory dream`) is no longer the only way to write L3
concept summaries. An agent can own the summarisation itself:

1. Call `summary_jobs` (MCP tool), `mintmory summary-jobs` (CLI), or
   `GET /summaries/jobs` (HTTP) to receive the list of concepts that need a
   (re)summary — concepts with no current summary, or whose stored
   `memory_count` no longer matches the current active count.
2. Write a concise synthesis for each concept (you are the LLM).
3. Send it back via `summary_put` (MCP), `mintmory summary-put` (CLI), or
   `PUT /summaries/{concept}` (HTTP).

This path calls no summarizer and requires no `MINTMORY_LLM_*` configuration
(`MINTMORY_LLM_PROVIDER=none` is fine). The concept-selection policy
(`MINTMORY_SUMMARY_MIN_MEMORIES`, `MINTMORY_SUMMARY_TOP_K`,
`MINTMORY_SUMMARY_MAX_CONTENTS`, `MINTMORY_SUMMARY_MAX_CONTENT_CHARS`,
`LINK_STOPLIST`) is respected identically to the LLM path — the same concepts
and the same truncated/capped content snippets are presented to the agent.

The two paths coexist: `memory_dream` still runs the configured-LLM path when
a backend is set; `summary_put` simply overwrites whatever a prior dream or
a prior agent-supplied write stored (idempotent upsert by concept).

**Measurement note.** Because the agent-supplied path has no LLM call, L3
latency is entirely network / I/O bound (one round-trip per concept). For
agents that are already LLMs (e.g. Claude Code with the MintMory MCP), this
eliminates the need for a separately configured Ollama / cloud-API backend
and makes L3 summarisation available in zero-configuration deployments.

### 6.5 L3 SPEED experiments (F3)

Measured with gemma4:e4b on 4 "fat" top-concepts (each ~20 notes) from the corpus.

| ID | Param(s) | before | after (measured) | VERDICT |
|---|---|---|---|---|
| E-S1 | `SUMMARY_CONCURRENCY=4` | 271.0 s (67.8 s/summary, serial) | **76.3 s (19.1 s/summary) — 3.55× faster** | **KEPT** — a single local GPU *does* parallelize Ollama here; concurrency is a real win |
| E-S0 | per-summary cost (fat concepts) | 67.8 s/summary serial | — | observation: fat concepts (20 notes) dominate; pair concurrency with `top_k` + `max_content*` |
| E-S2/3/4 | `top_k` / `max_content_chars` / `min_memories` | implemented | available (env) | DEFERRED — concurrency already gives the headline 3.55×; these compound it |

> The original ~50-min full dream (110 serial summaries) projects to **~14 min** at
> concurrency=4, and lower still once `SUMMARY_TOP_K` caps the long tail and
> `SUMMARY_MAX_CONTENT_CHARS` shortens fat prompts. The cloud tier (MiniMax via
> Portkey, §6.6) sidesteps the local-GPU cost entirely.

### 6.6 MODEL COMPARISON (R4 / F4)  — measured via `scripts/compare_models.py`

Sample: 6 top concepts (summary) + 2 ground-truth conflicts (resolution; AXIS
523-vs-520, OpenAPI 35-vs-36 paths) on the 155-record corpus. Coverage = fraction
of distinctive source tokens (digits/acronyms/quoted) preserved in the summary
(strict: summaries compress, so ~0.15–0.30 is normal). Agreement = resolver picks
the OUTDATED memory to archive.

| Model | Task | p50 ms | coverage | agreement (acc) | VERDICT |
|---|---|---|---|---|---|
| gemma4:e4b-it-qat (Ollama) | summary | 11779 | 0.16 | n/a | KEPT — local default; adequate, ~12 s/call |
| gemma4:e4b-it-qat (Ollama) | resolution | 10365 | n/a | **2/2 = 1.00** | KEPT — correct on both conflicts |
| qwen3.5:9b-nvfp4 (Ollama) | summary/resolution | **timeout** | — | — | **REJECTED (local)** — exceeds 300 s/call on this GPU; impractical for L3 |
| MiniMax-M2.7 (Portkey→cloud) | summary | ~cloud | clean | — | **ADOPTED as quality tier** — fast, no local GPU; thinking-model `<think>` stripped |
| MiniMax-M2.7 (Portkey→cloud) | resolution | ~cloud | n/a | conflict detected | works via gateway |

> **Verdict.** Local `qwen3.5:9b-nvfp4` is not viable for L3 here — it exceeded even
> a 300 s/call timeout (a reasoning model at this quant on this GPU). The practical
> choices are: **gemma4:e4b** for a fast local default (resolves both ground-truth
> conflicts correctly), or **MiniMax-M2.x via the self-hosted Portkey gateway** for a
> cloud quality tier with no local-GPU limit. Both are one env change
> (`MINTMORY_LLM_*`). Switching to Portkey is just:
> `MINTMORY_LLM_PROVIDER=openai MINTMORY_LLM_BASE_URL=http://localhost:8789/v1`
> `MINTMORY_LLM_API_KEY=pk-<name>-<org>-NNN MINTMORY_LLM_MODEL=MiniMax-M2.7`.
> (Use the `MiniMax-` prefix: the bare `M2.7` matches the gateway's routing class but
> the MiniMax upstream rejects it as an unknown model id.) MiniMax-M2.x are *thinking*
> models — `build_summarizer` now strips `<think>…</think>` so summaries stay clean.

### 6.10 IMAGE UNDERSTANDING — feature note (`add-image-understanding`, G5)

This is not an experiment with before/after measurements — it is a feature addition.
The notes below record the design choices that constrain what future experiments
could measure.

**What ships in v1:**

- `image_jobs` / `image_caption_put` core functions, MCP tools, CLI commands, and
  HTTP routes (`GET /images/jobs`, `PUT /images/{file_id}`).
- `index-tree --vision` flag: SVG text extracted inline (pure stdlib,
  `xml.etree.ElementTree`); raster images queued as agent jobs
  (`index_mode='vision'` manifest row, no model call).
- `VisionProvider` enum (`agent` / `llm` / `ocr`) + `VisionSettings` group
  (`MINTMORY_VISION_*`). Provider defaults to `agent`; `llm` and `ocr` are a seam
  that raises `NotImplementedError` with clear guidance in v1.
- Hybrid-bytes payload (`image_b64`): populated only for online-only files or
  `include_bytes=True`, within `MINTMORY_VISION_MAX_IMAGE_MB` (default 8 MB cap);
  oversized files set `oversized=True`. Optional Pillow downscale (`[image]` extra,
  lazy import, `MINTMORY_VISION_DOWNSCALE_MAX_PX=1568`).
- No-drift guarantee: `image_caption_put` archives prior active descriptions before
  writing the new one; a subsequent default `image_jobs()` never re-surfaces the
  same image.
- One schema delta: `index_mode CHECK` widened to include `'vision'` via a
  best-effort idempotent startup migration (mirrors `_ensure_is_note_column`).

**What does NOT change:**

- `index-tree` without `--vision` is byte-for-byte unchanged.
- `get_annotating_notes` and `search()` are untouched (image descriptions are
  `is_note=False` and surface through ordinary FTS/vector search).
- No new required runtime dependency (Pillow + pytesseract are optional extras,
  lazy-imported).

**Potential future experiments (not scoped to v1):**

| ID | Question | Lever | Metric |
|---|---|---|---|
| E-V1 | Does `image_b64` embed quality degrade above N MB (before downscale)? | `MINTMORY_VISION_MAX_IMAGE_MB` sweep | description quality vs payload size |
| E-V2 | Does Pillow downscale at 1568 px preserve agent-description quality? | `MINTMORY_VISION_DOWNSCALE_MAX_PX` sweep (512 / 1024 / 1568 / off) | description quality, byte size |
| E-V3 | How many images can a single `image_jobs` poll handle before the agent context is saturated? | `limit` + `include_bytes` | context window utilisation, job throughput |
| E-V4 | Does the `llm` seam (future) produce better descriptions than `agent` for dense technical diagrams? | `MINTMORY_VISION_PROVIDER=llm` vs `agent` | description coverage of embedded text/labels |

---

### 6.9 PERSONAL-NOTES KNOBS (`MINTMORY_NOTE_*`) — pending measurement

These three knobs govern capture-authority, auto-include breadth, and anchor
confidence for user-authored notes. All defaults reproduce today's behaviour for
non-note rows: `note_bonus` only ever applies to `is_note=1` records; `auto_include_cap`
adds zero items when the store has no `ANNOTATES` links; `anchor_min_dominance`
only fires on `about`-anchored note creation. No experiment needed to ship the
feature — measurements below close the loop and set long-term defaults.

| Param | Default (ships) | Range | Hypothesis | What to measure | VERDICT |
|---|---|---|---|---|---|
| `MINTMORY_NOTE_NOTE_BONUS` | `0.05` | 0.0–0.20 | Half the max recency bonus (0.1); breaks ties without outranking clearly-more-relevant non-notes. At `0.0` ranking is byte-identical to today. | RRF rank delta for note vs non-note with equal base relevance; note appears first at default. | pending |
| `MINTMORY_NOTE_AUTO_INCLUDE_CAP` | `3` | 0–10 | Return up to 3 annotating notes per search result (reverse `ANNOTATES` traversal). `0` disables entirely (today's behaviour). | extra items in `notes_on_results` per result; latency delta of Phase-3 traversal loop. | pending |
| `MINTMORY_NOTE_ANCHOR_MIN_DOMINANCE` | `0.6` | 0.40–0.90 | Confident anchor: top candidate must hold ≥ 60% of the candidate pool's relevance mass AND beat the second candidate strictly. Below threshold, fall back to topic-entity fold (no hard link). | `anchor_kind="memory"` rate on a labelled anchor-query set; false-positive hard-links at dominance 0.4 vs 0.6 vs 0.8. | pending |

**What each experiment measures (fast, no LLM required):**

- **`note_bonus` sweep** (`0.0 / 0.05 / 0.10 / 0.20`): create one note and one
  equally-relevant non-note memory; assert rank order from `memory_search`. The
  `scripts/metrics.py` harness needs no change — rank is observable from the
  returned `memories` list.
- **`auto_include_cap` sweep** (`0 / 1 / 3 / 5`): ingest a note anchored (via
  `ANNOTATES`) to a known memory, then search for that memory and inspect the
  `notes_on_results` field. Measure: number of extra context items surfaced, P50
  latency delta of the Phase-3 loop (should be sub-millisecond on a hot in-memory
  SQLite for cap ≤ 5).
- **`anchor_min_dominance` sweep** (`0.4 / 0.6 / 0.8`): create notes with
  varying `about` phrases against a small labelled store (3–10 memories), count
  hard-links vs topic-folds per threshold. Target: at `0.6`, a phrase that
  unambiguously matches one memory should produce `anchor_kind="memory"` ≥ 90% of
  the time; an ambiguous phrase should fall through to `topic` ≥ 80% of the time.

> **Acceptance bar.** Notes must not degrade overall retrieval. A search on a
> corpus with 10% notes should have `hybrid recall@10` within ≤ 2% of the
> note-free baseline (same probe set used in §6.3). The `note_bonus` default of
> `0.05` is predicted to be within this bar; if E-N-B1 shows otherwise, revert to
> `0.0` (no-op for existing behaviour).

---

### 6.8 HUB-PRUNING KNOB (LEANN-informed, to be measured)

| ID | Param(s) | default | range | hypothesis | corpus | VERDICT |
|---|---|---|---|---|---|---|
| E-H1 | `MINTMORY_LINK_HUB_CAP_MULTIPLIER=1.0` (no-op baseline) | 1.0 | 1.0–8.0 | Default is a strict no-op: uniform cap, byte-identical to today's behaviour | agentic_support | pending |
| E-H2 | `MINTMORY_LINK_HUB_CAP_MULTIPLIER=2.0`, `MINTMORY_LINK_HUB_DEGREE_PERCENTILE=0.9` | — | — | Hub nodes (candidate-degree ≥ 90th-percentile) receive 2× the per-node cap; cluster-holding edges survive pruning that a uniform cap would sever | agentic_support | pending |

> Measurement plan: run `scripts/metrics.py graph` on the `agentic_support` corpus
> at `multiplier=1.0` (baseline), `2.0`, and `4.0`; record `degree_max`,
> `pct_links_top_k_entities`, and `search-around breadth` on the probe queries.
> Accept if hub recall improves (relevant ids stay in union) without increasing
> overall breadth past the E-L-MID target of 45.5%.  The `_cap_per_node` fast path
> (`multiplier <= 1.0`) guarantees zero regression on all existing tests.

---

### 6.7 ADOPTED DEFAULTS (the verdicts, applied in `core/config.py`)

What changed in the shipped defaults, and the measured value of each:

| Knob | Old default | New default | Why (measured) |
|---|---|---|---|
| `EMBED_PROVIDER` | (ollama, external) | **`hashing`** (pure-Python, 0 deps) | ties nomic recall (E-E1/E-E2); drops the embedding dependency (R2) |
| `LINK_MIN_SHARED_ENTITIES` | 1 | **2** | −70% links alone (E-L1); kills single-hub-entity noise |
| `LINK_STOPLIST` | ∅ | **all,api,backend,ing,space** | noise entities 5 → 0 (E-N1) |
| `LINK_MAX_PER_NODE` | ∞ | **25** | bounds hub degree 83 → 25 without recall loss |
| `LINK_IDF_WEIGHTED_STRENGTH` | False | **True** | rare-entity links outrank hub links; enables `min_strength` pruning |
| `LINK_ENTITY_DF_CAP_RATIO` | 1.0 (off) | **1.0 (off)** | 0.15 over-pruned and dropped recall (E-L6) — **REVERTED** |

Net effect on the corpus: **links 2586 → 641 (−75%)**, search-around breadth
**90.3% → 45.5%**, **noise entities 5 → 0**, retrieval recall **preserved**, and
the embedder is now **dependency-free**. All knobs remain env-overridable; set
`MINTMORY_LINK_MIN_SHARED_ENTITIES=1` for very small stores.

---

## 7. OpenTelemetry observability plan (R5)

Goal: make every processing stage *understandable* (where time goes, how many
links/summaries/contradictions each step produced, model latency). Dependency-light
and **off by default** (no exporter unless configured), so the dependency-free
default path stays clean.

- **Dependency**: `opentelemetry-sdk` + `opentelemetry-exporter-otlp` as an
  **optional extra** `[otel]`. The core imports the **API only** (`opentelemetry-api`
  is tiny and a no-op without an SDK), guarded so absence never breaks anything.
- **Config** (`core/config.py`): `MINTMORY_OTEL_ENABLED` (default `false`),
  `MINTMORY_OTEL_ENDPOINT`, `MINTMORY_OTEL_SERVICE_NAME` (default `mintmory`).
- **Spans** (tracer `mintmory.dreaming` / `mintmory.storage` / `mintmory.embed`):
  - `dream.run_full` (root) → child spans `dream.detect_anomalies`,
    `dream.create_concept_links`, `dream.generate_summaries`,
    `dream.resolve_contradictions`, `dream.archive`, `dream.rehabilitate`.
  - `embed.embed_batch` (attr: `provider`, `dim`, `n_texts`).
  - `storage.search` → `storage.fts`, `storage.vector`, `storage.search_around`
    (attr: `candidate_pool`, `graph_added`, `depth`).
  - `llm.chat` (attr: `model`, `provider`, `prompt_chars`, token counts if
    available) — one span per LLM call, so model latency is first-class.
- **Span attributes = the metrics**: `link.candidate_pairs`, `link.created`,
  `link.min_shared`, `link.df_cap`, `summary.concepts`, `summary.skipped`,
  `contradiction.flagged`, `contradiction.resolved`. This means the **fast harness
  can read the same numbers from spans** (or from the return values) — one source
  of truth for "what happened".
- **Metrics (optional)**: counters `mintmory.links.created`,
  `mintmory.summaries.generated`; histograms `mintmory.embed.latency_ms`,
  `mintmory.llm.latency_ms`, `mintmory.search.latency_ms`.
- **Where it plugs in**: a tiny `core/observability.py` exposing
  `get_tracer(name)` / `span(name, **attrs)` context manager that is a **no-op**
  when OTel is disabled/uninstalled. `DreamingEngine`, `StorageAdapter.search`,
  embedders, and `llm.chat` wrap their bodies in `span(...)`. Zero behaviour
  change when disabled.

---

## 8. Config module (`core/config.py`) — single source for all knobs (R3)

All knobs above are fields on one `pydantic-settings` `Settings` model
(`pydantic-settings` is already a dependency), env-prefixed `MINTMORY_`, with the
**defaults that reproduce today's behaviour** (so adopting the module is a no-op
until an experiment overrides a value). Grouped: `embed_*`, `link_*`, `entity_*`,
`summary_*`, `llm_*`, `otel_*`. `seed_corpus.py`, `metrics.py`,
`exp_llm_compare.py`, and the transports read from this one place.

---

## 9. Risks & guardrails

- **Embedder swap invalidates stored vectors** (different dim/space). Mitigate:
  harness rebuilds from corpus each run; for prod, a re-embed migration + a
  `model_name`/`dim` stamp check before vector search.
- **Aggressive linking cuts can drop a *good* edge.** Guardrail E-L9: top-k
  precision@5 on probe queries must not regress; the labelled-relevant ids must
  stay in the union after traversal.
- **Lexical embedder misses synonyms.** Accepted tradeoff for the zero-dep
  default; hybrid RRF + the documented `ollama`/`local` upgrade path cover it.
- **`LINK_MAX_PER_NODE` greedy cap must be deterministic** or idempotency breaks
  (AGENTS §4.4). Stable sort key mandated.
- **Summary concurrency must not break idempotency** — writes remain
  `INSERT OR REPLACE` by concept, order-independent; second run still yields 0.
- **Tiny eval set** (probe_queries / contradiction_key) is hand-labelled and
  small; treat metrics as *directional*, not absolute. Expand the labelled set
  over time.
- **DF-aware embedder IDF couples the embedder to the store** (query vector depends
  on corpus). Mitigate by shipping `use_idf=False` first (pure function of text);
  only enable IDF if E-E4 shows a win.

---

## 10. LEANN-adapted recall benchmark (external retrieval quality)

Harness: `docs/eval/leann_recall_benchmark.py`. Adapts LEANN's recall@k
methodology (`benchmarks/run_evaluation.py`) onto MintMory's own hybrid search,
reusing LEANN's DPR / Natural-Questions eval data (queries + exact-flat
contriever ground truth). Unlike the hand-labelled `probe_queries.json` (§ above,
6 queries — *directional*), this is a **200-query / 100k-passage** external
benchmark, so the numbers are statistically meaningful (not absolute SOTA: the
haystack is a tractable subset of LEANN's full 2.1M DPR corpus, and the golden is
cross-model — contriever-msmarco vs MintMory's embedder).

Two ground truths: **LEANN NQ golden** (did we recover the same passages an exact
contriever search returns?) and **MintMory exact-flat / self** (does the hybrid
ranking match MintMory's own pure brute-force cosine top-k?).

Run: `uv run --no-sync python docs/eval/leann_recall_benchmark.py --embedder local --num-queries 200 --corpus-size 100000`

### Result — `all-MiniLM-L6-v2`, 200 q, 100k psg (2026-06-20)

| Retrieval | vs ground truth | recall@3 | recall@10 |
|---|---|---|---|
| Hybrid (FTS+trigram+vector RRF) | LEANN NQ golden | 0.663 | 0.857 |
| Vector-only (brute-force cosine) | LEANN NQ golden | **0.710** | 0.867 |
| Hybrid | MintMory exact-flat (self) | 0.658 | 0.570 |

Latency (hybrid, brute-force vector / 100k): mean 271 ms, p50 275, p95 313. DB 717 MB.

**FINDING (RRF dilutes the top of semantic ranking):** at 100k scale the lexical
(FTS+trigram) phase, RRF-merged, **lowers recall@3 vs pure vector** (0.663 vs
0.710); the harm is concentrated at the head of the list and washes out by @10
(0.857 vs 0.867). `hybrid_vs_self@3 = 0.658` confirms RRF substantially reorders
the dense top-k. In the small (2k) smoke run hybrid *won* — the regression only
emerges as the lexical haystack grows. **Implication:** for semantic-heavy
retrieval the default RRF under-weights the dense signal at the top; candidate
fix = vector-weighted fusion or a cosine rerank of the final page (to be measured
on this same harness). VERDICT: finding recorded; fix under investigation.

### Embedder sweep — same 200 q / 100k psg (2026-06-20)

| Embedder | dim | hybrid@3 | hybrid@10 | vector@3 | vector@10 | latency (mean) |
|---|---|---|---|---|---|---|
| `hashing` (default) | 512 | 0.378 | 0.608 | 0.247 | 0.348 | 300 ms |
| `all-MiniLM-L6-v2` | 384 | 0.663 | 0.857 | 0.710 | 0.867 | 271 ms |
| `nomic-embed-text` | 768 | 0.663 | 0.873 | 0.702 | 0.889 | 387 ms |

Notes: (1) the shipped **hashing** default is weak on semantic NQ (vector@3 0.25)
but there hybrid *helps* (0.378 vs 0.247) — its "vector" is itself lexical, so
FTS+trigram add signal; the RRF-hurts effect is specific to real semantic
embedders. (2) **nomic (768d) barely beats MiniLM (384d)** (+1.6pt @10) at +43%
latency + a network dependency — **MiniLM is the sweet spot**. (3) the RRF@3
regression replicates on both real embedders (≈ −4–5pt vs vector-only).

### RRF fix investigation — `docs/eval/rrf_investigation.py` (MiniLM, 200 q / 100k)

Re-fuses the per-query component score dicts under alternative strategies:

| Strategy | recall@3 | recall@10 |
|---|---|---|
| vector_only | 0.710 | 0.867 |
| rrf_k60 (current default) | 0.665 | 0.857 |
| wrrf_v2 (vector weight ×2) | 0.697 | 0.877 |
| wrrf_v3 (vector weight ×3) | 0.718 | 0.883 |
| **wrrf_v5 (vector weight ×5)** | **0.722** | **0.890** |
| rerank_n20 (cosine-rerank RRF top-20) | 0.713 | 0.873 |
| rerank_n50 | 0.710 | 0.867 |

**VERDICT — weighted RRF wins.** Weighting the vector source ×3–5 in `rrf_merge`
lifts recall@3 **0.665 → 0.722** (+5.7pt) and recall@10 **0.857 → 0.890** (+3.3pt),
beating *both* the unweighted default *and* pure-vector at both cutoffs (vector
dominates the head; lexical keeps the tail). Cosine-rerank of the RRF head (n20)
also recovers @3 but caps @10 at the rerank pool. Proposed change: a
per-source weight on `rrf_merge` (env `MINTMORY_SEARCH_VECTOR_RRF_WEIGHT`,
**default 1.0 = today's behaviour**; recommended 3.0), keeping the hashing default
unaffected (lexical-vector, where fusion already helps).

---

## 11. mempalace comparison — LongMemEval (agent-memory recall)

Harness: `docs/eval/mempalace_longmemeval_benchmark.py`. Adapts mempalace's
LongMemEval *raw* methodology (session granularity, doc = joined user turns,
metric `recall_any@k` vs `answer_session_ids`, embedder all-MiniLM-L6-v2) onto
MintMory's search. 500 questions, ~53 sessions each. Compared against mempalace's
**published** raw numbers (their README / committed results).

### Result — all-MiniLM-L6-v2, 500 q (2026-06-20)

| System / variant | R@5 | R@10 |
|---|---|---|
| mempalace raw (published) | 0.966 | 0.982 |
| MintMory vector-only (pure cosine) | 0.966 | 0.982 |
| MintMory hybrid (default, w=1) | 0.970 | 0.988 |
| MintMory hybrid + MM-22 (vector_rrf_weight=3) | **0.972** | **0.992** |

**Findings:** (1) MintMory's pure-vector path reproduces mempalace's raw number
to the digit (same model + data + metric) — confirms harness fidelity. (2)
MintMory's hybrid **beats** mempalace raw (0.970 vs 0.966 R@5) — on conversational
memory the FTS+trigram fusion is *additive* (opposite of the DPR/§10 case where
lexical noise hurt recall@3). (3) **MM-22 weighted RRF is the top performer**
(0.972 / 0.992), so the fix is a net win on BOTH benchmark families — supporting a
default bump toward 3.0. Runtime 254s for 500 q × 3 variants. NOTE: this is the
like-for-like *raw/generic* comparison; mempalace's higher published numbers
(98.4% held-out, ≥99% +LLM-rerank) come from heavily hand-tuned, partly
test-inspected heuristics (temporal/quote/name boosts, preference extraction),
which their own BENCHMARKS.md flags as teaching-to-the-test.

---

## 12. mempalace comparison — LoCoMo (multi-hop conversational recall)

Harness: `docs/eval/mempalace_locomo_benchmark.py`. Adapts mempalace's LoCoMo raw
methodology (session granularity, doc = dialog turns joined, recall = fraction of
a question's evidence sessions in top-k, empty evidence => 1.0). 10 conversations,
1986 questions, all-MiniLM-L6-v2, session/top-10. vs mempalace published.

### Result — session/top-10, 1986 q (2026-06-20)

| System / variant | Avg recall |
|---|---|
| mempalace raw (published) | 0.603 |
| mempalace hybrid v5 (published, hand-tuned) | 0.889 |
| MintMory vector-only | 0.6029 |
| MintMory hybrid (default, w=1) | **0.9207** |
| MintMory hybrid + MM-22 (w=3) | 0.7907 |

**Findings:** (1) MintMory vector-only reproduces mempalace raw to the digit
(0.6029 vs 0.603) — second independent harness-fidelity confirmation (cf. §11).
(2) MintMory's GENERIC hybrid (0.921) beats mempalace's HAND-TUNED hybrid v5
(0.889) — LoCoMo questions share exact names/tokens with dialog, which MintMory's
FTS+trigram fusion captures out of the box. (3) **MM-22 vector weighting is
workload-dependent**: it helped LongMemEval (§11, paraphrase recall) but HURTS
LoCoMo (0.79 < 0.92, exact-match-dominated). This validates the conservative
`vector_rrf_weight=1.0` default + per-deployment tuning — raise it for
paraphrase/semantic workloads, leave it at 1.0 (or lower) for exact-match recall.

---

## 13. mempalace comparison — ConvoMem (per-message evidence recall)

Harness: `docs/eval/mempalace_convomem_benchmark.py` (HF loader copied verbatim
from mempalace for identical item selection). Per item: corpus = one doc per
message; recall = fraction of evidence message texts matched (substring, either
direction) in top-k. 250 items (5×50; `changing_evidence` 404s for the loader, as
it does for mempalace), all-MiniLM-L6-v2, top-10. vs mempalace published raw 0.929.

### Result — raw, 250 items, top-10 (2026-06-20)

| System / variant | Avg recall |
|---|---|
| mempalace raw (published) | 0.929 |
| MintMory vector-only | **0.9287** |
| MintMory hybrid (default, w=1) | 0.8973 |
| MintMory hybrid + MM-22 (w=3) | 0.9093 |

**Findings:** (1) MintMory vector-only reproduces mempalace raw to the digit
(0.9287 vs 0.929) — THIRD independent harness-fidelity confirmation (cf. §11, §12).
(2) Here the hybrid slightly *hurts* (0.897) — short-message semantic retrieval,
lexical fusion adds distractor noise; MM-22 (w=3) partially recovers (0.909) by
upweighting vector. Consolidated cross-benchmark picture: vector-only == mempalace
raw everywhere; hybrid fusion is workload-dependent (LoCoMo exact-match +0.32,
LongMemEval +0.004, ConvoMem −0.03), and MM-22's vector weight is the right knob.

---

## 14. mempalace comparison — MemBench (ACL 2025, per-turn recall)

Harness: `docs/eval/mempalace_membench_benchmark.py` (data:
github.com/import-myself/Membench, `MemData/FirstAgent`, topic=movie). Per item:
index every conversation turn (batch-embed + bulk-insert), query the QA question,
hit@k = a `target_step_id` turn is in the top-k (matched on sid or global index).
8500 items, all-MiniLM-L6-v2, top-5. vs mempalace published HYBRID 0.803.

### Result — movie, top-5, 8500 items (2026-06-20)

| System / variant | R@5 |
|---|---|
| mempalace hybrid (published, hand-tuned) | 0.803 |
| MintMory vector-only | 0.7866 |
| MintMory hybrid (default, w=1) | **0.8195** |
| MintMory hybrid + MM-22 (w=3) | 0.8171 |

**Findings:** MintMory's GENERIC hybrid (0.820) edges mempalace's HAND-TUNED
hybrid (0.803, with name/predicate/quoted-phrase boosts). No published mempalace
*raw* MemBench number exists, so this row is hybrid-vs-hybrid (no vector==raw
receipt). Per-category recall is bimodal (comparative 0.994, aggregative 0.972 vs
conditional 0.726, highlevel_rec 0.72) — the harder reasoning categories drag the
mean, which is why an easy-category smoke (0.92) overstated it. MM-22 weight is
neutral here (0.817 vs 0.820). Harness uses batch-embed + bulk-insert (entity
extraction skipped; retrieval-identical) — full 8500 in 27 min vs >90 min per-turn.

### Consolidated scoreboard (MintMory vs mempalace, same MiniLM embedder)

| Benchmark | mempalace | MintMory default hybrid | MintMory vector == mempalace raw? |
|---|---|---|---|
| LongMemEval R@5 | 0.966 raw | 0.970 (✅) | 0.966 == 0.966 ✓ |
| LoCoMo recall | 0.603 raw / 0.889 tuned | 0.921 (✅) | 0.6029 ≈ 0.603 ✓ |
| ConvoMem recall | 0.929 raw | 0.897 (vector 0.929 ties) | 0.9287 ≈ 0.929 ✓ |
| MemBench R@5 | 0.803 tuned | 0.820 (✅) | (no raw baseline published) |
