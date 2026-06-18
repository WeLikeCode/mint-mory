# MintMory — LLM Settings, Model Comparison & OpenTelemetry Observability

Status: DESIGN (additive, parameterized, safe-defaults). This document owns the
LLM-provider seam (R3), the model-comparison experiment (R4), the L3 summary
performance fix (the slow-summaries finding), and the OpenTelemetry plan (R5).

It is a sibling to the embedding/entity/graph design (those parameters live in
`docs/EXPERIMENTS.md` / the graph design doc). Anything written here is **off by
default unless stated** — the default `mintmory-core` install stays dependency-light
and runs with **no Ollama, no torch, no OTel**.

Source-of-truth hierarchy is unchanged: `types.py > schema.sql > openapi.yaml`.
Nothing here touches the schema. All new behaviour is config-gated.

---

## 0. Design ground rules (so this stays additive)

1. **One config module.** All env-driven knobs land in a new
   `packages/core/src/mintmory/core/config.py` built on `pydantic-settings`
   (already a core dependency). No scattered `os.environ.get` in business logic.
2. **The only allowed external dependency is the LLM backend** (summaries +
   contradiction resolution). It sits behind `LLMSettings` and is trivially
   swappable by env. Embeddings move to the pure-Python core default
   (see `docs/EXPERIMENTS.md`); `scripts/local_llm.py` becomes **LLM-only**.
3. **`provider=none` is the default and it must be a no-op.** With no LLM
   configured, `run_light`/`run_full` skip L3 summaries and contradiction
   resolution (counts return 0) — exactly the current `summarizer=None` /
   `conflict_resolver=None` behaviour, now reached through config instead of
   ad-hoc wiring.
4. **Observability is a shim.** When `MINTMORY_OTEL_ENABLED` is false (default)
   every span/metric call is a no-op with zero import cost. `opentelemetry-sdk`
   is an **optional extra** (`mintmory-core[otel]`), never a hard dependency.
5. **Every parameter change is a tracked experiment** (R1): each has a default,
   a plausible range, a hypothesis, the metric it moves, and a recorded
   kept/reverted VERDICT in the experiment log (`docs/experiments/LOG.md`).

---

## 1. LLM provider abstraction + settings (R3)

### 1.1 The seam already exists

`DreamingEngine` already takes two injected callables and treats `None` as
"skip the step":

```python
# packages/core/src/mintmory/core/dreaming.py (current)
Summarizer       = Callable[[str, list[str]], str]
ConflictResolver = Callable[[MemoryRecord], list[BatchResolutionAction]]

class DreamingEngine:
    def __init__(self, adapter, summarizer=None, conflict_resolver=None): ...
    # generate_summaries():     returns 0 when self.summarizer is None
    # resolve_contradictions(): returns 0 when self.conflict_resolver is None
```

We do **not** change `DreamingEngine`'s signature. We add a *builder* that turns
`LLMSettings` into those two callables (or `None` when `provider=none`). This
keeps `dreaming.py` pure and testable (canned callables in unit tests) while
giving scripts/transports a single "build me a configured engine" entry point.

### 1.2 `core/config.py` — the settings model

New module. Pure pydantic-settings; importing it pulls in nothing heavy.

```python
# packages/core/src/mintmory/core/config.py
from __future__ import annotations
from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    NONE   = "none"     # default — no LLM; L3 + contradiction resolution skipped
    OLLAMA = "ollama"   # OpenAI-compatible local endpoint (Ollama, LM Studio, vLLM)
    OPENAI = "openai"   # OpenAI / any OpenAI-compatible hosted endpoint


class EmbeddingProvider(str, Enum):
    HASH   = "hash"     # default — pure-Python in-process embedder (see EXPERIMENTS.md)
    LOCAL  = "local"    # sentence-transformers (optional [local] extra)
    OLLAMA = "ollama"   # Ollama /v1/embeddings (optional, network)
    OPENAI = "openai"   # OpenAI embeddings (optional [openai] extra)


class LLMSettings(BaseSettings):
    """Config for the summarization / contradiction-resolution LLM ONLY.

    This is the single external dependency MintMory permits (R3). Everything is
    env-driven with a fully offline default (provider=none → L3 skipped)."""
    model_config = SettingsConfigDict(env_prefix="MINTMORY_LLM_", extra="ignore")

    provider:    LLMProvider = LLMProvider.NONE
    base_url:    str  = "http://localhost:11434/v1"  # OpenAI-compatible base
    model:       str  = "gemma4:e4b-it-qat"
    api_key:     str | None = None                    # injected as Bearer when set
    timeout_s:   float = Field(default=60.0, ge=1.0, le=600.0)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # L3 perf knobs (see §3):
    summary_top_k:  int = Field(default=40, ge=0)     # 0 = no cap (legacy behaviour)
    summary_min_memories: int = Field(default=3, ge=2)


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_EMBED_", extra="ignore")
    provider: EmbeddingProvider = EmbeddingProvider.HASH
    model:    str | None = None      # provider-specific (ollama/openai)
    base_url: str | None = None
    api_key:  str | None = None
    dim:      int | None = None      # override; HASH default 256 (see EXPERIMENTS.md)


class OTelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_OTEL_", extra="ignore")
    enabled:  bool = False
    exporter: str  = "console"       # "console" | "otlp"
    # OTLP endpoint/headers come from the standard OTEL_EXPORTER_OTLP_* vars,
    # honoured natively by the SDK; we do not re-implement them.
    service_name: str = "mintmory"
```

Env var summary (all optional; defaults give a fully offline core):

| Env var | Default | Meaning |
|---|---|---|
| `MINTMORY_LLM_PROVIDER` | `none` | `none` \| `ollama` \| `openai` |
| `MINTMORY_LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `MINTMORY_LLM_MODEL` | `gemma4:e4b-it-qat` | chat model id |
| `MINTMORY_LLM_API_KEY` | _(unset)_ | Bearer token (hosted/openai) |
| `MINTMORY_LLM_TIMEOUT_S` | `60` | per-call timeout (s) |
| `MINTMORY_LLM_MAX_CONCURRENCY` | `4` | bounded parallel LLM calls (§3) |
| `MINTMORY_LLM_TEMPERATURE` | `0.0` | sampling temperature |
| `MINTMORY_LLM_SUMMARY_TOP_K` | `40` | cap concepts summarised (§3); 0=uncapped |
| `MINTMORY_LLM_SUMMARY_MIN_MEMORIES` | `3` | min memories before a concept is summarised |
| `MINTMORY_EMBED_PROVIDER` | `hash` | pure-Python default (see EXPERIMENTS.md) |
| `MINTMORY_OTEL_ENABLED` | `false` | turn the OTel exporter on (§4) |
| `MINTMORY_OTEL_EXPORTER` | `console` | `console` \| `otlp` |
| `MINTMORY_OTEL_SERVICE_NAME` | `mintmory` | resource `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(SDK default)_ | standard OTel var, honoured as-is |

### 1.3 `core/llm.py` — provider client + builders (new)

This is the **only** module that talks to a chat LLM. It replaces the
chat/contradiction logic currently living in `scripts/local_llm.py`. It depends
on stdlib `urllib` + `json` only (no `openai` SDK required — the OpenAI-compatible
`/chat/completions` shape is identical across Ollama, LM Studio, vLLM and OpenAI).

```python
# packages/core/src/mintmory/core/llm.py  (sketch)
class LLMClient:
    """Thin OpenAI-compatible /chat/completions client (stdlib only)."""
    def __init__(self, settings: LLMSettings): ...
    def chat(self, prompt: str) -> str:
        # POST {base_url}/chat/completions with model/temperature/timeout;
        # add `Authorization: Bearer {api_key}` iff api_key is set.
        # Wrapped in an OTel span "llm.chat" (model, prompt_tokens,
        # completion_tokens, latency_ms) — see §4.

def build_summarizer(settings: LLMSettings) -> Summarizer | None:
    if settings.provider is LLMProvider.NONE:
        return None
    client = LLMClient(settings)
    def summarize(concept: str, contents: list[str]) -> str:
        return client.chat(SUMMARY_PROMPT.format(...)).strip()
    return summarize

def build_conflict_resolver(settings, adapter) -> ConflictResolver | None:
    if settings.provider is LLMProvider.NONE:
        return None
    client = LLMClient(settings)
    def resolve(record): ...  # moved verbatim from local_llm.make_conflict_resolver
    return resolve

def build_dreaming_engine(adapter, settings: LLMSettings | None = None) -> DreamingEngine:
    settings = settings or LLMSettings()
    return DreamingEngine(
        adapter,
        summarizer=build_summarizer(settings),
        conflict_resolver=build_conflict_resolver(settings, adapter),
    )
```

Two prompt templates already exist in `core/prompts.py`
(`CONTRADICTION_DETECTION_PROMPT`, `FEEDBACK_PROMPT`). We add `SUMMARY_PROMPT`
there (moving the literal currently inline in `local_llm.ollama_summarizer`) so
all LLM contracts stay in one audited module (AGENTS.md §4.1 keeps the
contradiction schema correct).

### 1.4 `scripts/local_llm.py` becomes LLM-ONLY

- **Delete** `OllamaEmbedder` and the `EMBED_MODEL`/`EMBED_DIM`/`/embeddings`
  code path from `local_llm.py`. Embeddings are now the core's pure-Python
  default (`EmbeddingProvider.HASH`); an Ollama/OpenAI embedder, if anyone wants
  one, is an opt-in built from `EmbeddingSettings` in the embedder factory — not
  in this script.
- **Keep** `chat`, `extract_json`, `check_contradiction`, the summarizer prompt,
  and `make_conflict_resolver`, but have them delegate to `core/llm.LLMClient`
  (constructed from `LLMSettings`) instead of reading `OLLAMA_*` directly. The
  script becomes a thin back-compat shim around `core/llm.py`.
- `scripts/seed_corpus.py` change: `embedder = None` (default HASH embedder is
  applied by the storage/factory layer); replace the hand-wired
  `DreamingEngine(summarizer=..., conflict_resolver=...)` with
  `build_dreaming_engine(store, LLMSettings())`. With `provider=none` the seed
  runs fully offline (L1 + L2 graph only); set `MINTMORY_LLM_PROVIDER=ollama` to
  enable L3 + contradiction resolution.

### 1.5 Default behaviour matrix

| `MINTMORY_LLM_PROVIDER` | summaries (L3) | contradiction resolution | external dep |
|---|---|---|---|
| `none` (default) | skipped (count 0) | skipped (count 0) | **none** |
| `ollama` | on, via local `/v1` | on | local Ollama |
| `openai` | on, via hosted `/v1` | on | OpenAI (api_key) |

This satisfies R3: the only external dependency is the LLM backend, fully
env-selected, and the default ships dependency-free with L3 disabled.

---

## 2. Model comparison experiment (R4)

Goal: compare `gemma4:e4b-it-qat` vs `qwen3.5:9b-nvfp4` on **(a)** summary
quality, **(b)** contradiction-resolution correctness, **(c)** latency — cheaply
and repeatably, recording results in the experiment log.

### 2.1 Harness: `scripts/compare_models.py` (new)

Single script, takes a model list and a built corpus DB. It does **not** rebuild
the corpus (rebuild is slow); it reads an existing `/tmp/mintmory_corpus.db`.

```
uv run python scripts/compare_models.py \
    --db /tmp/mintmory_corpus.db \
    --models gemma4:e4b-it-qat,qwen3.5:9b-nvfp4 \
    --base-url http://localhost:11434/v1 \
    --sample 8 \
    --out docs/experiments/model_compare_<date>.json
```

For each model it constructs `LLMSettings(provider=ollama, model=<m>)` and runs
three sub-evaluations on a **fixed sample** (deterministic: temperature 0, fixed
concept/seed list, so the only variable is the model):

### 2.2 (a) Summary quality — LLM-judge + cheap rubric

- Pick `--sample` concepts deterministically: the **top-K by frequency** from the
  existing corpus stats (`get_stats().top_concepts`), excluding known noise
  concepts (`all`, `api`, `backend`, `ing`, `space` — the 5 flagged in the
  baseline). This gives a stable, meaningful sample (~8 concepts) instead of 110.
- Generate a summary with each candidate model.
- Score each summary two ways:
  1. **Deterministic rubric (no LLM):** specificity proxy = count of concrete
     tokens preserved from source memories (digits, ALL-CAPS acronyms, quoted
     spans, URLs) that survive into the summary / total in source; plus a length
     guard (penalise < 1 sentence or > 4 sentences). Cheap, reproducible.
  2. **LLM-judge (one strong judge, same for both candidates):** judge model =
     `gpt-oss:20b` (the strongest local model available; held fixed so it does
     not bias toward either candidate). Prompt asks for a 1–5 score on
     {faithfulness, specificity, conciseness} given the source memories and the
     candidate summary; return JSON `{faithfulness, specificity, conciseness}`.
     Average the three.

### 2.3 (b) Contradiction-resolution correctness — known ground truth

The corpus contains **labelled conflicts with a known-correct resolution**. Two
canonical cases (verified in `scripts/corpus_parts/02_inghub.json`):

| Conflict | Memories | Correct resolution |
|---|---|---|
| **AXIS Victoriei credentials** | README summary says **523** credentials (port 2580) vs live `GetCredentialList` returns **520** (port 2580) | Prefer the **live GetCredentialList (520)**; the README summary is the outdated one → DELETE/supersede the 523 memory |
| **AXIS Dacia credentials** | README summary says **521** (port 2480) vs live `GetCredentialList` returns **518** (port 2480) | Prefer **live 518**; archive the 521 README summary |
| **TYPED_SCHEMA link-type count** | a "9 link types" memory vs the correct **11** in `types.py` (`ConceptLinkType` is an 11-value closed enum) | Prefer **11**; supersede the "9"/"7" memory |

(The AGENTS-cited "TYPED_SCHEMA 9-vs-7" is the same shape: pick the value that
matches the authoritative count.)

Procedure per model:
1. Flag the two memories of each pair (`flagged_for_review=1`,
   `contradicts_ids` cross-linked) on a **throwaway copy** of the DB
   (`cp` the file first; never mutate the shared corpus DB).
2. Run `build_conflict_resolver(settings, adapter)(flagged_record)`.
3. Score: **correct** iff the resolver returns `action=DELETE` (or `UPDATE`
   superseding) targeting the *outdated* memory id (the README/9 one), **wrong**
   if it targets the live/authoritative one, **abstain** if `NONE`/unparseable.
   Report correct / wrong / abstain counts and accuracy = correct / total.

This is 2–3 calls per model — cheap, and the ground truth is unambiguous.

### 2.4 (c) Latency

Wrap every chat call in the OTel `llm.chat` span (§4); the harness also records
wall-clock `latency_ms` per call directly (so it works with OTel off). Report
p50/p95 latency per model and mean tokens/call (`usage` from the response when
present).

### 2.5 Recording results

The harness writes a JSON artifact under `docs/experiments/model_compare_<date>.json`:

```json
{
  "date": "2026-06-15", "base_url": "...", "sample": 8,
  "models": {
    "gemma4:e4b-it-qat": {
      "summary": {"rubric_mean": 0.62, "judge_mean": 3.4},
      "contradiction": {"correct": 2, "wrong": 0, "abstain": 1, "accuracy": 0.67},
      "latency_ms": {"p50": 26900, "p95": 31000}, "tokens_mean": 180
    },
    "qwen3.5:9b-nvfp4": { ... }
  },
  "verdict": "qwen wins contradiction (3/3) at ~1.7x latency; gemma adequate for summaries"
}
```

A one-line VERDICT is appended to `docs/experiments/LOG.md` with the
before/after numbers and a kept/reverted decision (e.g. "set
`MINTMORY_LLM_MODEL` default to qwen3.5:9b-nvfp4 — KEPT" or "reverted, gemma
cheaper and summaries indistinguishable"). This satisfies R1's tracked-experiment
requirement and R4's recording requirement.

---

## 3. L3 summary performance fix

**Finding:** full run ≈ 50 min because summaries are serial (~27 s/summary on
gemma over 110 concepts). Two independent, composable levers:

### Lever A — cap to top-K concepts by frequency (`summary_top_k`)

`generate_summaries` currently summarises **every** entity in ≥ `min_memories`
active memories (sorted by concept name). Change it to:

1. Build `entity_to_contents` as today.
2. Keep only entities with `len(contents) >= summary_min_memories`.
3. Sort those by `len(contents)` **descending**, take the first
   `summary_top_k` (when `summary_top_k > 0`; `0` keeps the legacy "all" path).

Rationale: the long tail of rare concepts adds the most calls for the least
value, and the noise concepts (`all`, `api`, …) are exactly the high-frequency
ones we'd otherwise want — so K must be paired with a **noise stoplist**
(shared with the entity-extraction work in `docs/EXPERIMENTS.md`; the stoplist is
applied *before* the top-K cut). This keeps idempotency intact: the upsert guard
in `generate_summaries` is unchanged, so a re-run on an unchanged DB still
returns 0.

- **Parameter:** `summary_top_k` — default **40**, range **20–110** (110 ≈
  current "all"). Hypothesis: K=40 covers the concepts that actually carry
  decision value while cutting calls ~64% (110→40). Metric: `new_summaries`
  count + total L3 wall-time; quality regression checked via §2's rubric on the
  dropped vs kept concepts (spot-check 5 dropped concepts add no unique synthesis).

### Lever B — bounded-concurrency LLM calls (`max_concurrency`)

The summarizer calls are independent; run them through a bounded pool. Since the
calls are blocking HTTP, use a `concurrent.futures.ThreadPoolExecutor(max_workers=
settings.max_concurrency)` **inside the builder-provided summarizer batch path**,
not inside `DreamingEngine` (keeps the engine pure). Concretely: add an optional
`generate_summaries` fast path that, when the injected summarizer exposes a
`batch(items) -> list[str]` capability, fans the calls out concurrently; the
default serial callable keeps the simple contract for unit tests.

- **Parameter:** `max_concurrency` — default **4**, range **1–8** (local GPU
  serialises beyond a point; 1 = today's serial behaviour). Hypothesis: at K=40
  and concurrency=4, full L3 drops from ~50 min to **~4–5 min** (40 × 27 s / 4 ≈
  4.5 min). Metric: L3 wall-time at fixed K; watch for endpoint 5xx/timeouts as
  concurrency rises (back off to the timeout/`max_concurrency` cap).

**Combined target:** K=40 + concurrency=4 → **~3–5 min** full dream (down from
~50 min), a ~10× speedup, with quality held by the noise stoplist + spot-check.
Both are env-tunable and revert to legacy behaviour at `summary_top_k=0`,
`max_concurrency=1`.

---

## 4. OpenTelemetry plan (R5)

### 4.1 Principles

- **Off by default, zero-cost when off.** A no-op shim is used unless
  `MINTMORY_OTEL_ENABLED=true`. The `opentelemetry-*` packages are an **optional
  extra** (`mintmory-core[otel]`); importing the shim never imports the SDK.
- **Standard semantics.** Use the OTel GenAI semantic conventions for LLM spans
  (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`) so traces render in any OTel-aware backend.
- **One instrumentation seam.** A single `telemetry.py` module exposes a
  decorator + context manager + counters/histograms. No raw OTel calls anywhere
  else in the codebase.

### 4.2 File layout

```
packages/core/src/mintmory/core/
    telemetry.py        # NEW — shim + (optional) SDK init; @traced, span(), metrics
    config.py           # NEW — OTelSettings (above)
```

`telemetry.py` structure:

```python
# No hard import of opentelemetry at module top.
_ENABLED = False
def init_telemetry(settings: OTelSettings | None = None) -> None:
    """Idempotent. If settings.enabled: import opentelemetry, set up a
    TracerProvider + MeterProvider with a console or OTLP exporter and the
    standard OTEL_* env (endpoint/headers). Otherwise leave the no-op shims."""

# Seam 1 — context manager
@contextmanager
def span(name: str, **attrs): ...     # no-op when disabled; real span when enabled

# Seam 2 — decorator
def traced(name: str | None = None):  # wraps a function in span(name or func.__qualname__)
    ...

# Seam 3 — metrics (lazy instruments; no-op when disabled)
def add_count(name: str, value: int = 1, **attrs): ...
def record_value(name: str, value: float, **attrs): ...
```

When disabled, `span()` yields a dummy object whose `.set_attribute` is a no-op,
`traced` returns the function unchanged, and the metric helpers return
immediately — so instrumented hot paths (`add_memory`, `search`) pay nothing.

### 4.3 Spans to emit

| Span | Where | Key attributes |
|---|---|---|
| `mintmory.add_memory` | `StorageAdapter.add_memory` | `category`, `n_entities`, `has_embedding` |
| `mintmory.search` | `StorageAdapter.search` | `query_len`, `limit`, `n_fts`, `n_vec`, `n_results`, `search_around` |
| `mintmory.search_around` | `StorageAdapter.search_around` | `n_anchors`, `depth`, `n_link_types`, `min_strength`, `n_found` |
| `mintmory.embed` | embedder `embed`/`embed_batch` | `provider`, `model`, `dim`, `batch_size`, `latency_ms` |
| `mintmory.dream.full` / `.light` | `DreamingEngine.run_*` | `new_links`, `new_summaries`, `resolved`, `archived`, `rehabilitated`, `duration_ms` |
| `mintmory.dream.step` | each of steps 1–6 | `step` (`anomaly`/`link`/`summary`/`resolve`/`archive`/`rehab`), `count` |
| `gen_ai.chat` (LLM call) | `LLMClient.chat` | `gen_ai.system`=provider, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `latency_ms`, `ok` |

Step spans are children of the dream span, and each `gen_ai.chat` span is a child
of the step that triggered it (summary or resolve) — so a trace shows the whole
dream tree with per-call model + token + latency, directly answering "why is the
dream slow / which model / which step".

### 4.4 Metrics to emit

| Instrument | Type | Labels |
|---|---|---|
| `mintmory.memories.added` | counter | `category` |
| `mintmory.searches` | counter | `had_vector` |
| `mintmory.search.latency_ms` | histogram | `phase` (`fts`/`vector`/`graph`/`total`) |
| `mintmory.embed.latency_ms` | histogram | `provider`, `model` |
| `mintmory.llm.calls` | counter | `model`, `kind` (`summary`/`resolve`/`contradiction`/`judge`), `ok` |
| `mintmory.llm.latency_ms` | histogram | `model`, `kind` |
| `mintmory.llm.tokens` | histogram | `model`, `direction` (`in`/`out`) |
| `mintmory.dream.duration_ms` | histogram | `intensity` |
| `mintmory.dream.summaries` / `.links` / `.resolved` | counter | — |

The `llm.*` metrics directly feed the §2 model-comparison report (latency/tokens
per model) and the §3 perf work (dream duration before/after K + concurrency).

### 4.5 Exporters & local viewing

- `MINTMORY_OTEL_EXPORTER=console` → `ConsoleSpanExporter` +
  `ConsoleMetricExporter` (PeriodicExportingMetricReader). Zero infra; spans/metrics
  print to stderr — enough to read a single dream's tree locally.
- `MINTMORY_OTEL_EXPORTER=otlp` → OTLP/HTTP exporter using the standard
  `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` env (e.g. a local
  Jaeger/Tempo/Grafana or `otel-tui`). We do not invent our own endpoint vars.
- Suggested local stack (docs only, not a dependency): `jaegertracing/all-in-one`
  on `:4318` for traces; `otel-tui` for a no-infra terminal view.

### 4.6 Optional extra

Add to `packages/core/pyproject.toml`:

```toml
[project.optional-dependencies]
otel = [
  "opentelemetry-sdk>=1.27",
  "opentelemetry-exporter-otlp-proto-http>=1.27",
]
```

Default install excludes it; `pip install 'mintmory-core[otel]'` enables real
export. If the extra is missing but `MINTMORY_OTEL_ENABLED=true`, `init_telemetry`
logs one warning via structlog and stays in no-op mode (never crashes).

---

## 5. Fast metric harness (cross-cutting, no LLM)

So L2/embedding/entity changes are measurable in **seconds** (not the ~50-min
L3 phase), a separate `scripts/graph_metrics.py` (owned by the graph design doc)
runs `run_light` with `summarizer=None` and prints: link count, degree
distribution (avg/median/max), % links from top-K entities, and a search-around
precision proxy on the known queries (`iOS cancel endpoint bug`,
`INGHub mobile delivery`). The LLM work in **this** doc is deliberately kept
*out* of that fast loop: §2 (model compare) and §3 (L3 timing) are run on demand,
not on every graph iteration. This keeps the design principle "measurement must
be fast" intact — graph/embedding experiments never wait on the LLM.

---

## 6. Summary of file changes (this doc's scope)

| File | Change |
|---|---|
| `packages/core/src/mintmory/core/config.py` | NEW — `LLMSettings`, `EmbeddingSettings`, `OTelSettings`, enums |
| `packages/core/src/mintmory/core/llm.py` | NEW — `LLMClient`, `build_summarizer`, `build_conflict_resolver`, `build_dreaming_engine` |
| `packages/core/src/mintmory/core/telemetry.py` | NEW — OTel shim: `init_telemetry`, `span`, `traced`, metric helpers |
| `packages/core/src/mintmory/core/prompts.py` | ADD `SUMMARY_PROMPT` (moved from `local_llm`) |
| `packages/core/src/mintmory/core/dreaming.py` | ADD bounded-concurrency summary fast-path + `summary_top_k`/stoplist (additive; serial path preserved); wrap steps in `span()` |
| `packages/core/src/mintmory/core/storage.py` | wrap `add_memory`/`search`/`search_around` in `span()` + metrics (no behaviour change) |
| `scripts/local_llm.py` | LLM-ONLY: drop `OllamaEmbedder`/embeddings; delegate chat to `core/llm.LLMClient` |
| `scripts/seed_corpus.py` | use `build_dreaming_engine(store, LLMSettings())`; default embedder = pure-Python HASH |
| `scripts/compare_models.py` | NEW — model comparison harness (§2) |
| `packages/core/pyproject.toml` | ADD `[otel]` optional extra |
| `docs/experiments/LOG.md` | NEW — append-only VERDICT log (shared with other design docs) |

All changes are additive and config-gated; the default `mintmory-core` install
runs offline (no Ollama, no torch, no OTel) with L3 disabled.
</content>
</invoke>
