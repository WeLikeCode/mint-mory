# Design & FROZEN interface contract — `add-trigram-substring-search`

Implementers MUST match these signatures, names, and behaviours exactly so the
work integrates across disjoint files. Where intuition and this doc disagree,
this doc wins.

## 1. `scoring.py` — variadic RRF (owns `rrf_merge`)

Make `rrf_merge` accept N ranked lists, skipping empty ones. **Backward
compatible** with the existing `rrf_merge(fts, vec)` calls and tests
(`rrf_merge({}, {}) == {}`, `rrf_merge({"a": 1.0}, {}) == {"a": 1/61}`).

```python
def rrf_merge(*score_dicts: dict[str, float], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion over N ranked score dicts (higher score = better
    rank within each list). Empty dicts are skipped. RRF(d)=Σ 1/(k+rank_i(d))."""
```

Behaviour: for each non-empty dict, rank its docs by score desc (rank starts at
1); a doc's fused score is the sum of `1/(k+rank)` across the lists it appears in.
Keep `k=60`.

## 2. `storage.py` — trigram source (owns all of these)

### 2a. Constructor flag
`__init__(..., enable_trigram: bool = True)` → store `self._enable_trigram`.
Add `self._trigram_loaded: bool = False` (mirrors `self._vec_loaded`).

### 2b. Best-effort creation — `_ensure_trigram(self, conn)`
Called at the end of `initialise()` (after `executescript` + commit). Wrap the
whole body in `try/except sqlite3.OperationalError` → on failure set
`self._trigram_loaded = False` and return (graceful degradation). If
`not self._enable_trigram`, return immediately (flag stays False).

> **Corruption fix (post-implementation).** The first cut used an
> **external-content** table (`content='memories'`) with `'delete'`-command
> triggers and a `'rebuild'` backfill — matching `memories_fts`. That path is
> broken for the *trigram* tokenizer: after a `'rebuild'` of pre-existing rows,
> the next UPDATE's `'delete'` raises **"database disk image is malformed"**
> (reproduced on the 15k-row live DB; passes in fresh test DBs that populate
> incrementally). Fix: a **standalone** trigram table (stores its own content)
> with **rowid-based** delete triggers and an `INSERT…SELECT` backfill — robust
> and `'rebuild'`-free. `_ensure_trigram` also **migrates** any legacy
> external-content table (detected via `content=` in its `sqlite_master.sql`):
> drop its triggers + table, then recreate standalone.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS memories_trigram USING fts5(content, tokenize='trigram');

CREATE TRIGGER IF NOT EXISTS memories_trigram_insert AFTER INSERT ON memories BEGIN
    INSERT INTO memories_trigram(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_trigram_update AFTER UPDATE ON memories BEGIN
    DELETE FROM memories_trigram WHERE rowid = old.rowid;
    INSERT INTO memories_trigram(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memories_trigram_delete AFTER DELETE ON memories BEGIN
    DELETE FROM memories_trigram WHERE rowid = old.rowid;
END;
```

Then **backfill existing rows once**: if `count(memories_trigram)==0` and
`count(memories)>0`, run
`INSERT INTO memories_trigram(rowid, content) SELECT rowid, content FROM memories`.
`conn.commit()`. Set `self._trigram_loaded = True`. (Cost: the standalone index
duplicates `content` — acceptable for substring recall.)

### 2c. Match expression — module function `_trigram_match_expr(query)`
```python
def _trigram_match_expr(query: str) -> str:
    """OR of quoted tokens >= 3 chars (trigram needs >=3); '' if none."""
```
Tokenise `[A-Za-z0-9]+`, keep tokens with `len >= 3`, lowercase, dedup preserving
order, wrap each in double quotes, join with ` OR `. No prefix `*` (substring is
inherent to trigram). `""` when no token qualifies (caller skips the phase).

### 2d. Scores — `_trigram_scores(self, query, limit)`
Return `{}` if `not self._trigram_loaded` or the match expr is empty. Else:
```sql
SELECT m.id AS id, bm25(memories_trigram) AS rank
FROM memories_trigram JOIN memories m ON m.rowid = memories_trigram.rowid
WHERE memories_trigram MATCH ? ORDER BY rank LIMIT ?
```
Wrap in `try/except sqlite3.OperationalError -> {}`. Return
`{id: -float(rank)}` (negate bm25 so higher = better), mirroring `_fts_scores`.

### 2e. `search()` fusion
Replace the current `if fts_scores and vec_scores / elif / else` block with:
```python
trigram_scores = self._trigram_scores(request.query, pool)
sources = [s for s in (fts_scores, trigram_scores, vec_scores) if s]
if not sources:
    base_scores = {}
elif len(sources) == 1:
    base_scores = sources[0]
else:
    base_scores = scoring.rrf_merge(*sources)
```
Keep the existing **min-max [0,1] normalisation** of `base_scores` that follows
(MM-13) unchanged. `vec_scores` keeps its MM-13 NULL-distance guard.

## 3. Tests (contract)

- **`test_scoring.py`**: variadic `rrf_merge` — fuse 3 dicts; a doc in all three
  outranks a doc in one; existing 2-arg cases still hold.
- **`test_search.py`**: substring — index `"firewall config"`; `search("wall")`
  returns it (impossible with porter FTS). Keep MM-13 tests green.
- **`test_storage.py`**: `memories_trigram` exists after `initialise()` and
  `_trigram_loaded` is True in this env; `enable_trigram=False` leaves it False
  and search still works.
- **`test_schema.py`**: do NOT add `memories_trigram` to `REQUIRED_TABLES` (it is
  best-effort, not part of the core schema.sql); optionally assert it is creatable.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`, `mypy`.

## 4. Out of scope
Per-column bm25 weighting (single content column), configurable `rrf_k` via env,
and a dedicated `SearchSettings` group — deferrable; the off-switch is the
`enable_trigram` constructor flag.
