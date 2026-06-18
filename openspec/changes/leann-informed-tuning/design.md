# Design & FROZEN interface contract — `leann-informed-tuning`

Implementers MUST match these signatures, names, defaults, and behaviours exactly.
Where intuition and this doc disagree, this doc wins. Overarching invariant
(MintMory config ethos): **every new default reproduces today's behaviour** so the
knob is a tracked experiment.

---

## 1. Hub-aware pruning

### 1a. `core/config.py` — `LinkSettings` additions
Add two fields (keep the module's commented-knob style):
```python
# Hub-aware pruning (LEANN-informed): give high-degree "hub" concepts a larger
# degree budget so a uniform cap can't sever the links that hold a cluster
# together. Defaults are a NO-OP (multiplier 1.0 == today's uniform cap).
hub_cap_multiplier: float = Field(default=1.0, ge=1.0, le=8.0)
hub_degree_percentile: float = Field(default=0.9, ge=0.5, le=1.0)
```

### 1b. `core/dreaming.py` — `_cap_per_node`
New signature (still a `@staticmethod`):
```python
@staticmethod
def _cap_per_node(
    candidates: list[_LinkCandidate],
    max_per_node: int,
    *,
    hub_cap_multiplier: float = 1.0,
    hub_degree_percentile: float = 0.9,
) -> list[_LinkCandidate]:
```
Caller (in `create_concept_links`) passes the settings:
```python
candidates = self._cap_per_node(
    candidates, ls.max_per_node,
    hub_cap_multiplier=ls.hub_cap_multiplier,
    hub_degree_percentile=ls.hub_degree_percentile,
)
```

Algorithm:
- **No-op fast path:** if `hub_cap_multiplier <= 1.0`, behave EXACTLY as today —
  uniform cap, same deterministic order `(-shared_count, -strength, src, tgt)`,
  same result. (This keeps every existing test green.)
- **Hub-aware path** (`hub_cap_multiplier > 1.0`):
  1. Compute each node's **candidate-degree** = number of candidates incident to
     it (count over both endpoints across all candidates).
  2. **Hub threshold** = nearest-rank value at `hub_degree_percentile` over the
     sorted list of per-node candidate-degrees: for `degs = sorted(degree.values())`,
     `threshold = degs[min(len(degs) - 1, floor(hub_degree_percentile * len(degs)))]`.
     A node is a **hub** iff its candidate-degree `>= threshold`.
  3. **Effective cap** per node: `int(max_per_node * hub_cap_multiplier)` if hub,
     else `max_per_node`.
  4. Greedy keep using the SAME deterministic order; a link survives iff both
     endpoints are under THEIR effective cap. Deterministic + idempotent.

No behaviour change unless a `MINTMORY_LINK_HUB_CAP_MULTIPLIER > 1.0` is set.

---

## 2. Pluggable vector phase — `core/storage.py`

Extract the existing inline brute-force vector block from `search()` into a method
(mirroring `_fts_scores` / `_trigram_scores`), **behaviour byte-identical**:
```python
def _vector_scores(
    self, query: str, query_embedding: np.ndarray | None, limit: int
) -> dict[str, float]:
    """Vector phase of hybrid search: brute-force cosine over stored embeddings.

    Returns {memory_id: -distance} (higher = better); {} when no embedder /
    sqlite-vec / embedding is available. NULL distances (mixed-dimension
    embeddings) are skipped. Isolated behind this method so an ANN backend can
    replace the scan later without touching search()/fusion (see ADR-0006).
    """
```
Move verbatim: the `_vector_search_available()` gate, the query-embedding/`_embed`
blob computation, the `vec_distance_cosine ... ORDER BY dist LIMIT ?` query, the
`try/except sqlite3.OperationalError`, and the **NULL-distance skip**. In
`search()`, replace the inline block with
`vec_scores = self._vector_scores(request.query, query_embedding, pool)`. The
`sources`/RRF/normalisation that follow are unchanged.

---

## 3. Re-embed guard — regression test only (no code change)

`update_memory` already does `embedding = self._embed(updated.content) if
content_changed else None` and only appends `embedding = ?` to the UPDATE when
content changed — verified. Add a test that asserts: updating a NON-content field
(e.g. `confidence`) does NOT call `_embed`, and updating `content` to a new value
DOES. (Spy on `self._embed` / count calls via monkeypatch.) No production change.

---

## 4. ADR-0006 — `docs/architecture/ADR-0006-vector-search-scale.md`

A short ADR in the existing ADR style. Decision: vector search stays **brute-force**
(documented as `_vector_scores`) until ~**100k–500k** memories (current high-water
~16k → 6–30× headroom; vector phase ~1–15 ms today, ~0.5–2 s near 1M). At the
threshold, adopt **`sqlite-vec`'s `vec0` ANN** once it reaches stable v1, else
**`hnswlib`** — both keep the single-file/light-dep ethos. **Never LEANN** (trades
latency up; FAISS+native-deps + second index format break the ethos; storage win
is inverted for the hashing embedder). Cite the crossover numbers and that the real
`.db` bloat is the trigram content duplication, not embeddings. Also add a one-line
`docs/EXPERIMENTS.md` entry for the hub-pruning knob (default off; to be measured).

---

## 5. Tests (contract)
- `test_dreaming.py`: (a) `hub_cap_multiplier=1.0` → identical kept-set to a
  uniform cap (no-op proof); (b) `hub_cap_multiplier=2.0` → a hub node retains more
  links than a non-hub under the same `max_per_node`. Deterministic/idempotent.
- `test_search.py`/`test_storage.py`: search results unchanged after the
  `_vector_scores` extraction (existing hybrid/vector tests stay green; add one
  asserting `_vector_scores` returns `{}` with no embedder and non-empty with one);
  the re-embed-guard test from §3.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`, `mypy --strict`.
