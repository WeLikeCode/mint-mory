# Design & FROZEN interface contract — `add-personal-notes`

Implementers MUST match these signatures, names, defaults, SQL, and behaviours
exactly. Where intuition and this doc disagree, this doc wins. Overarching
invariants:

- **MintMory config ethos:** every new default reproduces today's behaviour, so a
  knob is a tracked experiment.
- **Single-file SQLite**, three-transports-one-core: all domain logic lives in
  `mintmory.core`; MCP/CLI/API are thin wrappers that serialise `types.py`
  models.
- **No new runtime dependency.** No date parsing. Agent supplies ISO dates.
- Gates for every package touched: `pytest` (cov ≥ 80), `ruff check`,
  `ruff format --check`, `mypy --strict` (line-length 100).

A **note** is defined precisely as a `MemoryRecord` with `is_note == True`. By
construction `create_note` also sets `source = MemorySource.USER` and
`verified = True`, but the single load-bearing predicate everywhere downstream
(scoring, archival, contradiction, feedback, listing) is **`is_note`** — never
`source`/`verified`. Do not branch on `source`/`verified` for note behaviour.

---

## 1. Schema + types

### 1a. `core/types.py` — `MemoryRecord.is_note`
Add ONE field, immediately after `verified` (keep field grouping under the
"State flags" comment is also acceptable; placement must be consistent with the
column order decision in §1c — see note there):

```python
    is_note: bool = False  # user-authored "remember this" note (overlay flag)
```

Default `False` ⇒ every existing construction site and every existing row is a
non-note. No validator needed (Pydantic coerces SQLite `0/1` → bool as it does
for the other flags via `bool(row[...])`).

### 1b. `core/types.py` — `ConceptLinkType.ANNOTATES`
Add ONE enum member (asymmetric, note → item):

```python
    ANNOTATES = "annotates"  # A (a note) annotates B (the item it is about); inverse: annotated_by
```

It MUST **NOT** be added to `SYMMETRIC_LINK_TYPES` (an annotation has a
direction: the note is always the `source_memory_id`, the item the
`target_memory_id`). The enum now has 12 members; update the module docstring's
"11 typed" / "11 orthogonal" wording to 12 in `types.py` and the MCP server
`instructions` string ("11 typed ConceptLink relationships" → 12).

### 1c. `core/types.py` — `SearchResponse.notes_on_results`
Add ONE field to `SearchResponse`:

```python
    notes_on_results: dict[str, list[MemoryRecord]] = Field(default_factory=dict)
    # mapping {result_memory_id: [annotating note records]}, populated by the
    # ANNOTATES reverse-traversal auto-include (see §5b). Default empty = today.
```

Use `Field(default_factory=dict)` exactly (NOT `list`) — the value is a mapping
`{result_memory_id: [notes]}`. Default empty dict reproduces today's response.

### 1d. `core/schema.sql` — `is_note` column
Add the column to the `memories` table, in the "State flags" block, immediately
**after** `verified` is NOT where it lives in DDL (verified is in the provenance
block). Place it as the LAST state flag, after `contradicts_ids`, so the column
order is append-only and the migration (which always adds the column at the end
of the table) matches a fresh-create exactly:

```sql
    contradicts_ids     TEXT NOT NULL DEFAULT '[]',     -- JSON array of memory IDs
    is_note             INTEGER NOT NULL DEFAULT 0,      -- user-authored note overlay (0/1)
```

> Decision: **append `is_note` at the end of the logical column set** (after
> `contradicts_ids`, before the Timestamps block is fine — pick a single spot and
> keep `_MEMORY_COLUMNS` in lockstep). The only hard requirement is that
> `schema.sql`, `_MEMORY_COLUMNS`, `_memory_row_values`, and the `ALTER TABLE`
> default all agree. SQLite `ALTER TABLE ADD COLUMN` always appends physically;
> because INSERTs are column-named (not positional) this is safe regardless.

Add a partial index mirroring the existing flag-index style (used by the notes
surface + auto-include + archival guard):

```sql
CREATE INDEX IF NOT EXISTS idx_memories_note
    ON memories(is_note, valid_from)
    WHERE is_note = 1;
```

### 1e. `core/schema.sql` — `ANNOTATES` in the `concept_links` CHECK
Extend the `link_type` CHECK constraint list to include `'annotates'`:

```sql
    link_type           TEXT NOT NULL CHECK (link_type IN (
                            'relates_to','contradicts','refines','supersedes',
                            'enables','depends_on','similar_to','part_of',
                            'uses','before','valid_until','annotates'
                        )),
```

> Note: a CHECK constraint cannot be altered in place in SQLite. Pre-existing
> databases keep their old CHECK (which already lacks `annotates`). This is the
> SAME limitation the codebase already lives with for any enum addition; new
> `annotates` links written to an OLD db would violate the old CHECK. Mitigation
> is documented in §1f: the migration is **column-only**; for the link CHECK we
> rely on fresh databases. Implementers MUST add a test asserting a fresh DB
> accepts an `annotates` link, and the migration step (`_ensure_is_note_column`)
> MUST be tolerant if a future CHECK-rebuild is added. **Do not** attempt a
> table rebuild of `concept_links` in this change.

### 1f. `core/storage.py` — guarded migration (`_ensure_is_note_column`)
Mirror the trigram migration discipline exactly: introspect, then best-effort
add, wrapped so an old/locked DB degrades gracefully. Call it from
`initialise()` immediately after `_ensure_trigram(conn)`:

```python
def initialise(self) -> None:
    ...
    conn.executescript(ddl)
    conn.commit()
    self._ensure_trigram(conn)
    self._ensure_is_note_column(conn)   # NEW
```

```python
def _ensure_is_note_column(self, conn: sqlite3.Connection) -> None:
    """Best-effort, idempotent ALTER TABLE adding ``memories.is_note``.

    Fresh databases already have the column from schema.sql; this backfills it
    on pre-existing databases created before personal-notes. Uses the same
    PRAGMA table_info introspection + try/except pattern as the trigram
    migration: a failure (locked/old SQLite) degrades to "no notes" rather than
    crashing startup.
    """
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if "is_note" not in cols:
            conn.execute(
                "ALTER TABLE memories ADD COLUMN is_note INTEGER NOT NULL DEFAULT 0"
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass
```

Every pre-existing row gets `is_note = 0` (the column default) — i.e. existing
memories are all non-notes. Idempotent: the `PRAGMA table_info` check makes a
re-run a no-op.

### 1g. `core/storage.py` — column-order + (de)serialisation sync
Add `"is_note"` to `_MEMORY_COLUMNS` at the SAME logical position chosen in §1d
(append after `"contradicts_ids"`). Then:

- `_memory_row_values(...)` — add `_bool(record.is_note)` at the matching
  position.
- `_row_to_memory(...)` — add `is_note=bool(row["is_note"])`.
- `update_memory(...)` — add `"is_note = ?"` to `sets` and
  `_bool(updated.is_note)` to `params` at the matching position (so a note's flag
  round-trips through an update; note that `metadata`-only updates already
  preserve it).

These four lists (`_MEMORY_COLUMNS`, the INSERT values tuple, the UPDATE `sets`,
the UPDATE `params`) MUST stay in the same order — this is the existing
invariant; just extend it.

---

## 2. Config — `core/config.py` `NoteSettings` (`MINTMORY_NOTE_*`)

Add a new independent settings group (own env prefix), registered on `Settings`:

```python
# ---------------------------------------------------------------------------
# Personal notes (MINTMORY_NOTE_*) — capture + retrieval of user-authored notes.
# Defaults reproduce today's behaviour for non-note rows (note_bonus only ever
# applies to is_note=1; auto_include only adds ANNOTATES-linked notes).
# ---------------------------------------------------------------------------
class NoteSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_NOTE_", extra="ignore")

    # Additive authority boost in effective_score for is_note rows. Same scale as
    # the recency bonus (DECAY_BONUS_MAX = 0.1); a tie-breaker, not a hammer.
    note_bonus: float = Field(default=0.05, ge=0.0, le=1.0)
    # Max annotating notes auto-included per search result (reverse ANNOTATES
    # traversal). 0 disables auto-include.
    auto_include_cap: int = Field(default=3, ge=0, le=20)
    # Anchor resolution: minimum share of the candidate pool's relevance the top
    # candidate must hold to be treated as a confident/dominant hard-link match.
    anchor_min_dominance: float = Field(default=0.6, ge=0.0, le=1.0)
```

Register on the aggregate:

```python
class Settings(BaseSettings):
    ...
    note: NoteSettings = Field(default_factory=NoteSettings)
```

> `note_bonus=0.05` is half the max recency bonus (0.1) and on the same additive
> scale as the normalised `[0,1]` relevance — large enough to break ties, small
> enough not to outrank a clearly-more-relevant non-note. **It does NOT seed
> `usefulness_score`** (which would compound through feedback); it is applied at
> scoring time only.

---

## 3. Scoring — `core/scoring.py` `effective_score` note bonus

Add ONE optional parameter (defaulting to **0.0** so the function's behaviour is
unchanged for every existing caller) and a module constant:

```python
NOTE_BONUS: float = 0.05  # default authority boost for is_note rows (see NoteSettings)
```

```python
def effective_score(
    base_relevance: float,
    usefulness_score: float,
    staleness_score: float,
    last_accessed_at: datetime | None = None,
    usefulness_weight: float = USEFULNESS_WEIGHT,
    staleness_weight: float = STALENESS_WEIGHT,
    decay_rate: float = DEFAULT_DECAY_RATE,
    now: datetime | None = None,
    is_note: bool = False,
    note_bonus: float = 0.0,
) -> float:
    """... existing docstring ...

    When ``is_note`` is True, a flat ``note_bonus`` is added (authority boost for
    user-authored notes; same scale as the recency bonus). ``note_bonus`` defaults
    to 0.0 so non-note callers and unconfigured callers are unaffected.
    """
    return (
        base_relevance
        + usefulness_score * usefulness_weight
        - staleness_score * staleness_weight
        + recency_bonus(last_accessed_at, decay_rate=decay_rate, now=now)
        + (note_bonus if is_note else 0.0)
    )
```

> Default `note_bonus=0.0` (NOT `NOTE_BONUS`) so importing scoring changes
> nothing. The real value is threaded in by `search()` from `NoteSettings`
> (§5a). `MemoryRecord.effective_score` (the duplicate method on the model,
> types.py:162) is **left unchanged** — it is not used by `search()`; do not add
> the param there (keeps the diff minimal and avoids a second source of truth).

---

## 4. Capture — `core/notes.py` (NEW module)

A new module `packages/core/src/mintmory/core/notes.py` owns note creation,
anchor resolution, and listing. It depends only on `StorageAdapter`, `types`,
`config.NoteSettings`, and `entities.extract_entities`. No LLM, no network.

### 4a. `create_note(...)`

```python
def create_note(
    adapter: StorageAdapter,
    content: str,
    about: str | None = None,
    when: datetime | None = None,
    until: datetime | None = None,
    category: MemoryCategory | None = None,
    settings: NoteSettings | None = None,
) -> NoteResult:
    """Create a user-authored note (the ONE capture primitive).

    A note is a MemoryRecord with is_note=True, source=USER, verified=True.

    Args:
        content:  the note text (1..10_000 chars).
        about:    optional free-text "what this is about" anchor phrase. Resolved
                  conservatively (see 4b): a confident/dominant match becomes an
                  ANNOTATES hard-link; otherwise the phrase's entities are folded
                  into the note's entity_ids (topic anchor) and the raw phrase is
                  stashed in metadata['anchor'].
        when:     optional ISO date already parsed to a datetime by the transport
                  (the agent did NL->date). Stored in valid_from.
        until:    optional deadline datetime. Stored in valid_until.
        category: optional MemoryCategory override. Default: TEMPORAL when ``when``
                  is given, else EPISODIC.
        settings: NoteSettings (anchor dominance threshold). Defaults to
                  NoteSettings() (env-driven).

    Returns:
        NoteResult describing what was created and what it anchored to.
    """
```

Behaviour, in order:

1. `settings = settings or NoteSettings()`.
2. `category = category or (MemoryCategory.TEMPORAL if when is not None else
   MemoryCategory.EPISODIC)`.
3. Build and persist the note record via `adapter.add_memory(record=...)` with:
   `content`, `category`, `source=MemorySource.USER`, `verified=True`,
   `is_note=True`, `valid_from=when`, `valid_until=until`,
   `metadata={...}` (see anchor below). Entity extraction over `content` runs in
   `add_memory` as usual (the caller does not pre-supply `entity_ids`, so they
   are extracted from `content`).
4. If `about` is provided, run **anchor resolution** (§4b) which may (a) add an
   `ANNOTATES` link and set `metadata['anchor_memory_id']`, and/or (b) fold the
   anchor phrase entities into the note's `entity_ids`. In ALL cases store the
   raw phrase in `metadata['anchor']`.
5. Return `NoteResult`.

> Ordering detail: the note must be inserted **before** the `ANNOTATES` link
> (foreign-key: `concept_links.source_memory_id` references the note). After a
> hard-link or topic fold, the note's `entity_ids`/`metadata` are updated with a
> single `adapter.update_memory(note.id, entity_ids=..., metadata=...)` (avoid two
> writes). Because `update_memory` re-extracts entities ONLY when `content`
> changes, passing `entity_ids` explicitly here is safe and will be preserved.

### 4b. Anchor resolution algorithm (CONSERVATIVE)

Goal: turn a free-text `about` phrase into either a hard `ANNOTATES` link to one
existing memory OR a topic anchor (entities), never guessing wildly.

```python
def _resolve_anchor(
    adapter: StorageAdapter,
    note_id: str,
    about: str,
    settings: NoteSettings,
) -> tuple[str | None, list[str]]:
    """Resolve an ``about`` phrase. Returns (anchor_memory_id_or_None, entity_ids
    to fold in). Pure of side effects EXCEPT it may add_link the ANNOTATES edge."""
```

Algorithm:

1. **Candidate search.** Run a normal search over the existing store for the
   anchor phrase, EXCLUDING the just-created note and excluding other notes from
   becoming anchors:
   `req = SearchRequest(query=about, limit=5)` then `adapter.search(req)`.
   Filter the returned `memories` to `m.id != note_id and not m.is_note and not
   m.is_archived`. (Notes annotate *items*, not other notes.)
   - To keep anchor resolution side-effect-light, callers MAY instead use a
     dedicated read helper; but the simplest correct implementation reuses
     `adapter.search`. NOTE: `search` records a QuerySession + bumps retrieval
     counters. To avoid polluting decision-lineage with anchor lookups,
     implement a thin private read: `adapter._anchor_candidates(about, limit=5)`
     that runs `_fts_scores`/`_trigram_scores`/`_vector_scores` + `_load_memories`
     and returns scored `(score, MemoryRecord)` WITHOUT creating a session or
     bumping counters. **Use the dedicated helper.** (Signature below.)
2. **Dominance test.** Let `scores` be the candidate base-relevance scores
   (normalised to sum 1 over the candidate pool). If the pool is non-empty and
   the top candidate's share `>= settings.anchor_min_dominance` AND the top
   candidate is strictly ahead of the second (or is the only candidate):
   → **hard-link**: `adapter.add_link(ConceptLink(source_memory_id=note_id,
   target_memory_id=top.id, link_type=ConceptLinkType.ANNOTATES, entity=about,
   source=LinkSource.USER, strength=1.0, confidence=top_share))`. Return
   `(top.id, top.entity_ids)` — fold the anchored item's entities into the note
   too (so topic recall also finds it).
3. **Fallback to topic.** Otherwise (empty pool, or no dominant candidate):
   extract entities from the phrase via `extract_entities(about)` and return
   `(None, those_entities)`. No link is created.

```python
def _anchor_candidates(self, about: str, limit: int = 5) -> list[tuple[float, MemoryRecord]]:
    """Side-effect-free candidate lookup for note anchoring (no QuerySession, no
    retrieval-count bump). Reuses the hybrid score sources + min-max normalisation
    from search() but returns (normalised_score, record) pairs."""
```

> Edge cases the implementer MUST handle: empty store ⇒ topic anchor; `about`
> with no extractable entities ⇒ still store `metadata['anchor']`, fold nothing;
> ANNOTATES is asymmetric so `search_around` traversal (forward) from a note
> reaches the item, and reverse traversal from the item reaches the note (§5b).

### 4c. `NoteResult` (return shape) — in `core/types.py`

Add a small model next to the other result models:

```python
class NoteResult(BaseModel):
    """Outcome of create_note (what the note anchored to)."""

    note: MemoryRecord
    anchor_kind: Literal["memory", "topic", "none"]
    anchor_memory_id: str | None = None        # set when anchor_kind == "memory"
    anchor_entities: list[str] = Field(default_factory=list)  # entities folded in (topic/memory)
    anchor_phrase: str | None = None           # the raw ``about`` text, if any
```

`anchor_kind` semantics: `"memory"` = a hard ANNOTATES link was created;
`"topic"` = entities folded, no link; `"none"` = no `about` was supplied.

### 4d. `notes_list(...)`

```python
def notes_list(
    adapter: StorageAdapter,
    about: str | None = None,
    upcoming: bool = False,
    overdue: bool = False,
    limit: int = 50,
    now: datetime | None = None,
) -> list[MemoryRecord]:
    """List notes (is_note=1), newest-first by default.

    Filters (all optional, combinable):
      about:    only notes whose entity_ids contain ``about`` (case-insensitive)
                OR whose metadata['anchor'] contains it (case-insensitive substring).
      upcoming: only notes with valid_from > now, sorted soonest-first.
      overdue:  only notes with valid_from < now AND not archived (newest-first).
      limit:    cap (1..N).

    ``upcoming`` and ``overdue`` are mutually-exclusive temporal views; if both are
    True, raise ValueError (transports surface it as a 4xx / BadParameter).
    Archived notes are excluded unless neither temporal filter is set and the
    caller... (default: exclude archived). Returns MemoryRecord rows (is_note=True).
    """
```

Implemented over a new storage method `adapter.list_notes(...)` (§5c) so the SQL
lives in storage. Sorting:
- `upcoming`: `valid_from > now`, `ORDER BY valid_from ASC` (soonest first).
- `overdue`: `valid_from IS NOT NULL AND valid_from < now AND is_archived = 0`,
  `ORDER BY valid_from ASC` (most overdue first) — choose ASC and document it.
- neither: `ORDER BY created_at DESC` (newest note first), exclude archived.

---

## 5. Storage — `core/storage.py`

### 5a. `search()` — thread the note bonus
In the per-candidate scoring loop, pass the record's `is_note` and the configured
`note_bonus` into `scoring.effective_score`. `StorageAdapter` does NOT currently
hold settings; add an OPTIONAL `note_settings: NoteSettings | None = None`
parameter to `__init__` (default `None` ⇒ build `NoteSettings()` lazily, OR keep
`note_bonus` as a plain attribute). Concretely:

- Add to `__init__`: `note_bonus: float | None = None`. Store
  `self._note_bonus = note_bonus`. When `None`, resolve once lazily from
  `NoteSettings().note_bonus` (import inside the method to avoid a config import
  cycle, mirroring how CLI imports settings lazily). Default behaviour: callers
  that don't pass it get the configured `0.05`.

> Rationale for a constructor knob rather than reading env in `search()`: keeps
> `search()` pure-ish and unit-testable (`StorageAdapter(":memory:",
> note_bonus=0.0)` reproduces today's ranking exactly for tests). The three
> transports already build settings; they SHOULD pass
> `note_bonus=load_settings().note.note_bonus` when constructing the store, but
> the default keeps it working without that.

Scoring call becomes:

```python
eff = scoring.effective_score(
    base_relevance=base_scores.get(mem.id, 0.0),
    usefulness_score=mem.usefulness_score,
    staleness_score=mem.staleness_score,
    last_accessed_at=mem.last_accessed_at,
    now=now,
    is_note=mem.is_note,
    note_bonus=self._note_bonus,
)
```

### 5b. Auto-include annotating notes (reverse ANNOTATES traversal)
After the existing Phase-2 search-around block in `search()`, add a Phase-3
auto-include that, for each result, finds the notes that **annotate** it and
attaches them to `SearchResponse.notes_on_results`. This is a **reverse**
traversal of the asymmetric `ANNOTATES` edge: the result memory is the `target`,
the annotating note is the `source`.

New storage method:

```python
def get_annotating_notes(self, memory_id: str, cap: int) -> list[MemoryRecord]:
    """Return up to ``cap`` notes that ANNOTATE ``memory_id`` (reverse traversal of
    the asymmetric ANNOTATES edge: the note is the source, ``memory_id`` the
    target). Notes are ordered by link strength DESC, then created_at DESC.
    Archived notes are excluded. ``cap == 0`` returns []."""
    if cap <= 0:
        return []
    conn = self.connect()
    rows = conn.execute(
        "SELECT m.* FROM concept_links l "
        "JOIN memories m ON m.id = l.source_memory_id "
        "WHERE l.target_memory_id = ? AND l.link_type = ? "
        "AND m.is_note = 1 AND m.is_archived = 0 "
        "ORDER BY l.strength DESC, m.created_at DESC "
        "LIMIT ?",
        (memory_id, ConceptLinkType.ANNOTATES.value, cap),
    ).fetchall()
    return [self._row_to_memory(row) for row in rows]
```

In `search()`:

```python
# Phase 3: auto-include the notes annotating each result (reverse ANNOTATES).
notes_on_results: dict[str, list[MemoryRecord]] = {}
cap = self._auto_include_cap   # see below
if cap > 0:
    for mem in primary:
        annotating = self.get_annotating_notes(mem.id, cap)
        if annotating:
            notes_on_results[mem.id] = annotating
```

- Add `auto_include_cap: int | None = None` to `__init__` (same lazy-default
  pattern as `note_bonus`: `None` ⇒ `NoteSettings().auto_include_cap` = 3). Store
  as `self._auto_include_cap`.
- The auto-included notes are NOT added to `primary` (they are a SEPARATE channel
  on the response — `notes_on_results` — so they don't consume the `limit` slots
  or get double-counted in `total_found`). They are also NOT recorded as
  query_results and do NOT bump retrieval counters (they are context, not direct
  hits). Document this.
- Return them: `SearchResponse(..., notes_on_results=notes_on_results)`.

> A note that is itself a direct hit AND annotates another hit can appear both in
> `memories` and under `notes_on_results[other_id]` — that is acceptable and
> intentional (it is genuinely both).

### 5c. `list_notes(...)` (storage)

```python
def list_notes(
    self,
    *,
    entity: str | None = None,
    anchor_substr: str | None = None,
    upcoming: bool = False,
    overdue: bool = False,
    include_archived: bool = False,
    limit: int = 50,
    now: datetime | None = None,
) -> list[MemoryRecord]:
    """SQL backing for notes_list (§4d). Always filters is_note = 1.

    entity:        case-insensitive membership in entity_ids (post-filter in
                   Python, mirroring _passes_filter's entity check).
    anchor_substr: case-insensitive substring of metadata['anchor'] (post-filter).
    upcoming:      WHERE valid_from > now ORDER BY valid_from ASC.
    overdue:       WHERE valid_from IS NOT NULL AND valid_from < now
                   AND is_archived = 0 ORDER BY valid_from ASC.
    neither:       ORDER BY created_at DESC; exclude archived unless include_archived.
    """
```

Build the base SQL `SELECT * FROM memories WHERE is_note = 1`, append temporal
predicates with bound `now` (ISO string via `_iso`), apply `ORDER BY` + `LIMIT`,
then post-filter `entity`/`anchor_substr` in Python (consistent with how
`_passes_filter` handles `entity`). `upcoming and overdue` both True is rejected
at the `notes_list` layer (§4d) before reaching here.

### 5d. `apply_feedback` — stale-on-note flags instead of penalising
In `StorageAdapter.apply_feedback`, when `stale=True` AND the target row has
`is_note = 1`, do **not** increment `staleness_score` / set `is_stale`; instead
set `flagged_for_review = 1` and refresh `updated_at`. The `useful=True` path is
unchanged (notes can still be reinforced). Concretely, fetch `is_note` in the
existing SELECT and branch:

```python
row = conn.execute(
    "SELECT usefulness_score, staleness_score, reinforcement_count, is_note "
    "FROM memories WHERE id = ?",
    (memory_id,),
).fetchone()
...
note = bool(row["is_note"])
if useful:
    usefulness = scoring.increment_usefulness(usefulness, scoring.USEFUL_INCREMENT)
    reinforcement += 1
flag = 0
if stale:
    if note:
        flag = 1                      # flag a contested note for review
    else:
        staleness = scoring.increment_staleness(staleness, scoring.STALE_INCREMENT)
is_stale = 1 if staleness >= scoring.STALENESS_THRESHOLD else 0
```

Then the UPDATE must also set `flagged_for_review` when `flag == 1` (use
`flagged_for_review = MAX(flagged_for_review, ?)` semantics — i.e. only ever set
it to 1, never clear an existing flag). Simplest: add
`flagged_for_review = CASE WHEN ? = 1 THEN 1 ELSE flagged_for_review END` with
param `flag`. Document that a stale vote on a non-note is byte-identical to
today.

### 5e. Archival query guards (storage helpers used by dreaming/anomaly)
Add `AND is_note = 0` to the WHERE clause of:
- `get_never_accessed_stale(...)`
- `get_high_staleness_useful(...)`

so anomaly/archival surfaces never select notes. (These are read helpers used by
dreaming step 1; the actual archival SQL lives in `dreaming.archive_stale` — see
§6a.) This keeps notes out of "stale/never-accessed" anomaly reports too.

---

## 6. Dreaming — `core/dreaming.py`

### 6a. `archive_stale()` — exempt notes
Add `AND is_note = 0` to the archival SELECT so a note is **never** auto-archived
by staleness, regardless of its scores:

```python
rows = conn.execute(
    "SELECT id FROM memories "
    "WHERE is_stale = 1 AND staleness_score >= ? AND is_archived = 0 "
    "AND is_note = 0 "                              # NEW: notes are exempt
    "AND (last_accessed_at IS NULL OR last_accessed_at < ?) "
    "ORDER BY id",
    (scoring.ARCHIVE_THRESHOLD, cutoff),
).fetchall()
```

Also add `AND is_note = 0` to `detect_anomalies()`'s `never_accessed` and
`high_staleness_useful` queries (they are inline in dreaming.py, mirror §5e), so
the `AnomalyReport` never lists notes as stale/never-accessed anomalies.
(Notes CAN still appear in `contradictions` — that list is `flagged_for_review`,
which is exactly how a contested note surfaces for human review — see §6b.)

> Notes are still **rehabilitated**? No — a note never becomes `is_stale=1` via
> feedback (§5d), and `rehabilitate()` only touches `is_stale=1` rows, so notes
> are naturally untouched. No change needed in `rehabilitate()`; add a one-line
> comment noting the invariant. A note CAN be archived **explicitly** ("done")
> via `archive_memory` (§7) — that is intentional and separate from staleness
> archival.

### 6b. Contradiction authority — note wins; note-vs-note flags
The actual resolution decision today is produced by the **injected**
`conflict_resolver` (built in `llm.build_conflict_resolver`). To enforce note
authority deterministically WITHOUT depending on the LLM, add a pre-resolution
authority pass inside `DreamingEngine.resolve_contradictions()` (so it works even
with `provider=none`, where `conflict_resolver is None`).

New behaviour at the TOP of the per-flagged-memory loop in
`resolve_contradictions`, applied to each `flagged` record that is reachable
regardless of whether a resolver is configured:

For a flagged record `f` and each `other` in `f.contradicts_ids` (resolve via
`adapter.get_memory`):

1. If `f.is_note and not other.is_note` → **note wins**: supersede the
   non-note `other` (set `other.superseded_by = f.id`, `is_active=False`,
   `is_archived=True` via a new helper `_supersede(other_id, by_id)` that also
   records `metadata['superseded_by_note'] = f.id`), and clear `f.flagged_for_review`.
2. If `other.is_note and not f.is_note` → the **other note wins** symmetrically:
   supersede `f` by `other` and clear flags.
3. If `f.is_note and other.is_note` → **note-vs-note**: leave BOTH
   `flagged_for_review = 1` (do NOT auto-resolve, do NOT supersede) and add a
   `metadata['note_conflict_with']` breadcrumb on each. These remain in the
   `AnomalyReport.contradictions` list for human review. Skip the LLM resolver
   for this pair.
4. If neither is a note → fall through to the EXISTING resolver path unchanged.

Counting: each flagged record processed by the authority pass that gets resolved
(cases 1–2) counts toward `contradictions_resolved`; a note-vs-note pair (case 3)
does NOT count as resolved (it is deferred). The existing
`if self.conflict_resolver is None: return 0` early-return must be **relaxed**:
the authority pass (cases 1–3) runs even with no resolver; only case 4 needs the
resolver. Restructure so:
- iterate flagged memories;
- run the authority pass; if it fully handled the record (cases 1–3), continue;
- else, if `conflict_resolver is not None`, run the existing resolver path;
- else leave it flagged (no resolver, not a note conflict → unchanged from
  today, which would have returned 0 and touched nothing).

> Edge: a flagged note with EMPTY `contradicts_ids` and no resolver → stays
> flagged (correct: it was flagged by a stale-vote per §5d and awaits review).
> A `_supersede` helper is added to `StorageAdapter` (NOT a raw archive) so the
> supersede lineage (`superseded_by`) is set, matching the SUPERSEDES semantics:

```python
def supersede_memory(self, memory_id: str, by_id: str) -> None:
    """Mark ``memory_id`` superseded by ``by_id``: superseded_by=by_id,
    is_active=0, is_archived=1, refresh updated_at. (Used by note-authority
    contradiction resolution.)"""
    with self.transaction() as conn:
        conn.execute(
            "UPDATE memories SET superseded_by = ?, is_active = 0, is_archived = 1, "
            "updated_at = ? WHERE id = ?",
            (by_id, _iso(_utcnow()), memory_id),
        )
```

### 6c. Summaries — notes are inputs, never replaced
`generate_summaries()` already reads all active memories' content per entity; a
note's content is naturally included (no change needed — a note is active and
non-archived). The invariant "a note is never replaced by a summary" is already
true: `generate_summaries` writes `memory_summaries` rows and never archives or
mutates source memories. Add a one-line comment asserting this; **no code
change** in summary generation. Notes also participate normally in
`create_concept_links` (entity-based `relates_to`), which is desirable.

---

## 7. Marking a note done

"Done" is just archival of the note: reuse the existing `archive_memory`
(`is_archived=1, is_active=0`). No new core method. Exposed via the existing
archive transports (MCP `memory_archive`, HTTP `DELETE /memories/{id}`, and a CLI
note can be archived with... — the CLI has no archive command today; do **not**
add one in this change. Document that "done" = archive via MCP/HTTP). An archived
note: drops out of `notes_list` (default excludes archived), drops out of
`get_annotating_notes` (excludes archived), and stops getting the auto-include /
authority treatment.

---

## 8. Transports (thin)

All three mirror the existing patterns exactly. Each is a thin wrapper over
`core.notes` / `core.storage`; serialise via `model_dump(mode="json")` (MCP),
`response_model` (API), or rich tables (CLI).

### 8a. MCP — `packages/mcp/src/mintmory/mcp/server.py`
Two new `@mcp.tool()`s. The `memory_note` docstring MUST carry the **guardrail**.

```python
@mcp.tool()
def memory_note(
    content: str,
    about: str | None = None,
    when: str | None = None,        # ISO-8601 date/datetime; agent does NL->date
    until: str | None = None,       # ISO-8601 deadline
    category: str | None = None,
) -> dict[str, Any]:
    """Capture a user-authored note ("remember this about X").

    CALL THIS ONLY when the user EXPLICITLY asks you to remember something
    ("remember that...", "note that...", "don't forget..."). For facts you merely
    inferred or extracted, use memory_add instead — notes are higher-authority and
    are exempt from auto-archival.

    Args:
        content:  the thing to remember (1..10000 chars).
        about:    optional subject ("about my Tokyo trip"); anchored conservatively
                  to an existing memory if there's a confident match, else to its
                  topic (entities).
        when:     optional ISO-8601 date this note is salient ("2026-07-01"). YOU
                  convert natural language to ISO; MintMory does no date parsing.
        until:    optional ISO-8601 deadline.
        category: optional override; default temporal when `when` is set, else episodic.

    Returns:
        NoteResult dict: the stored note plus what it anchored to (anchor_kind:
        memory|topic|none, anchor_memory_id, anchor_entities, anchor_phrase).
    """
```

Implementation: parse `when`/`until` with `datetime.fromisoformat` (raise a clean
error dict `{"error": "bad_request", "message": ...}` on `ValueError`), coerce
`category` via `MemoryCategory(category)` when given, call
`notes.create_note(store, content, about=..., when=..., until=..., category=...)`,
return `result.model_dump(mode="json")`.

```python
@mcp.tool()
def notes_list(
    about: str | None = None,
    upcoming: bool = False,
    overdue: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List user-authored notes (is_note=true), newest-first.

    about:    filter to notes whose subject/entities mention this term.
    upcoming: only future-dated notes (valid_from in the future), soonest first.
    overdue:  only past-due notes (valid_from in the past), not archived.
    Returns a list of MemoryRecord dicts, each with is_note=true.
    """
```

Implementation: `notes.notes_list(store, about=..., upcoming=..., overdue=...,
limit=...)`; map the `ValueError` (both temporal flags) to an error dict;
`return [m.model_dump(mode="json") for m in records]`.

Update the server `instructions` string: bump "11 typed ConceptLink
relationships" → "12 typed ConceptLink relationships (incl. annotates)" and add a
sentence: "Use memory_note for explicit user 'remember this' requests; it marks a
note that is exempt from auto-archival and wins contradictions over inferred
memories."

### 8b. CLI — `packages/cli/src/mintmory/cli/main.py`
Two new `@app.command()`s. Mirror `add`/`search` style (rich output, `_parse_*`
helpers). Add a `_parse_iso(value: str | None) -> datetime | None` helper that
wraps `datetime.fromisoformat` and raises `typer.BadParameter` on failure.

```python
@app.command()
def note(
    content: str = typer.Argument(..., help="The thing to remember"),
    about: str | None = typer.Option(None, help="What this note is about (anchor)"),
    when: str | None = typer.Option(None, help="ISO date this note is salient (e.g. 2026-07-01)"),
    until: str | None = typer.Option(None, help="ISO deadline"),
    category: str | None = typer.Option(None, help="Override category (default temporal/episodic)"),
) -> None:
    """Capture a user-authored note ('remember this about X')."""
```

Body: build store via `_get_store()` (so the embedder is configured — anchor
resolution uses vector candidates), parse dates with `_parse_iso`, parse
`category` with `_parse_category` when given, call `notes.create_note(...)`,
print e.g. `Added note <id>` plus a line describing the anchor
(`-> annotates <anchor_memory_id>` / `-> topic: e1, e2` / no anchor).

```python
@app.command()
def notes(
    about: str | None = typer.Option(None, help="Filter by subject/entity"),
    upcoming: bool = typer.Option(False, "--upcoming", help="Future-dated notes, soonest first"),
    overdue: bool = typer.Option(False, "--overdue", help="Past-due notes (valid_from < now)"),
    limit: int = typer.Option(50, help="Max notes"),
) -> None:
    """List user-authored notes. Use --upcoming / --overdue for time views."""
```

Body: call `notes.notes_list(...)` (catch its `ValueError` → `typer.BadParameter`),
render a rich `Table` with columns `id`, `category`, `valid_from`, `content`
(show `valid_from` since the time views are the point), footer
`N note(s)`.

> Naming: the command is `notes` (plural) for listing and `note` (singular) for
> capture — distinct typer commands, no collision. (`mcp_serve` already shows the
> repo uses underscores for multi-word commands; these are single words.)

### 8c. HTTP API — `packages/api`
Add a request schema + two routes, plus update `docs/openapi/mintmory.yaml`.

`packages/api/src/mintmory/api/schemas.py` — new `NoteCreate`:

```python
class NoteCreate(BaseModel):
    """Request body for ``POST /notes``."""

    content: str = Field(..., min_length=1, max_length=10_000)
    about: str | None = None
    when: datetime | None = None       # ISO-8601; client/agent supplies the date
    until: datetime | None = None
    category: MemoryCategory | None = None
```

`packages/api/src/mintmory/api/app.py` — two routes (new "Notes" tag). The
response model for create is the new `NoteResult` (import from core types); for
list it is `list[MemoryRecord]`.

```python
@app.post("/notes", response_model=NoteResult, status_code=201, tags=["Notes"])
async def create_note(body: NoteCreate) -> NoteResult:
    """Create a user-authored note (is_note=true). See core.notes.create_note."""
    from mintmory.core import notes as notes_mod
    return notes_mod.create_note(
        get_store(),
        content=body.content,
        about=body.about,
        when=body.when,
        until=body.until,
        category=body.category,
    )

@app.get("/notes", response_model=list[MemoryRecord], tags=["Notes"])
async def list_notes(
    about: Annotated[str | None, Query()] = None,
    upcoming: Annotated[bool, Query()] = False,
    overdue: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[MemoryRecord]:
    """List notes. ``upcoming``/``overdue`` are mutually exclusive (422 if both)."""
    from mintmory.core import notes as notes_mod
    try:
        return notes_mod.notes_list(
            get_store(), about=about, upcoming=upcoming, overdue=overdue, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Add `NoteResult` to the `types` import in `app.py` and `NoteCreate` to the
`schemas` import. Mirror the OpenAPI YAML: add `NoteCreate`, `NoteResult`
schemas, `POST /notes`, `GET /notes`, and add `annotates` to the `ConceptLinkType`
enum + `is_note` to the `MemoryRecord` schema.

---

## 9. Determinism / invariants the implementer MUST preserve

- **Non-note ranking is byte-identical when `note_bonus=0.0`.** Tests construct
  `StorageAdapter(":memory:", note_bonus=0.0)` to prove search ordering is
  unchanged for non-notes.
- **The migration is idempotent** (PRAGMA check) and best-effort (try/except
  OperationalError) — second `initialise()` is a no-op; an old/locked DB does not
  crash.
- **ANNOTATES is asymmetric**: never in `SYMMETRIC_LINK_TYPES`; the note is
  always `source_memory_id`. Auto-include is a REVERSE traversal (item =
  `target_memory_id`).
- **Anchor lookups do not pollute decision-lineage** (use `_anchor_candidates`,
  not `search`).
- **Auto-included notes are a separate channel** (`notes_on_results`), not added
  to `memories`, not counted in `total_found`, not recorded as query_results, no
  retrieval bump.
- **A note is identified by `is_note`** everywhere — not by `source`/`verified`.
- **Notes are exempt from staleness archival** but CAN be archived explicitly
  ("done").
- **Note authority is deterministic** (works with `provider=none`); the LLM
  resolver only handles non-note-vs-non-note.
- **Idempotent dreaming preserved:** authority resolution clears flags / sets
  `superseded_by`, so a re-run sees no flagged memories for resolved pairs;
  note-vs-note stays flagged by design (a re-run re-detects it but makes no new
  change — assert the breadcrumb write is conditional so counts don't drift).

---

## 10. Tests (contract)

Group by ownership (see tasks.md). Minimum coverage:

- **schema/types/migration:** fresh DB has `is_note` column + accepts an
  `annotates` link; an old DB (table created without `is_note`) gains it via
  `_ensure_is_note_column` and existing rows read back `is_note=False`; second
  `initialise()` is a no-op; `MemoryRecord(is_note=True)` round-trips through
  add/get/update.
- **notes (create/anchor/list):** free note defaults to EPISODIC; note with
  `when` defaults to TEMPORAL and stores `valid_from`; `about` with a dominant
  match creates an ANNOTATES link + `anchor_kind="memory"`; `about` with no
  dominant match folds entities + `anchor_kind="topic"`; empty store ⇒ topic;
  `metadata['anchor']` always set when `about` given; `notes_list` upcoming/
  overdue ordering; both-flags ⇒ ValueError; `about` filter matches entity and
  anchor substring.
- **scoring/search:** `effective_score(is_note=True, note_bonus=0.05)` > same
  inputs as non-note; `note_bonus=0.0` reproduces today; a note and a non-note
  with equal base relevance ⇒ note ranks first; auto-include returns annotating
  notes capped at `auto_include_cap`, reverse-direction only (a forward
  ANNOTATES from the result does NOT pull it in), `cap=0` disables, archived note
  excluded, `notes_on_results` populated and `total_found` unchanged.
- **dreaming/feedback:** `archive_stale` skips a note even at staleness 10 /
  old `last_accessed_at`; `apply_feedback(stale=True)` on a note sets
  `flagged_for_review` and leaves `staleness_score`/`is_stale` untouched (and on
  a non-note is unchanged from today); note-vs-inferred contradiction supersedes
  the inferred (sets `superseded_by`) with `provider=none`; note-vs-note leaves
  both flagged and resolves nothing; anomaly report excludes notes from
  never-accessed/high-staleness.
- **transports:** MCP `memory_note`/`notes_list` happy-path + bad-ISO error dict;
  CLI `note`/`notes` (typer runner) incl. `--upcoming`/`--overdue` and bad date;
  API `POST /notes` 201 + `GET /notes` 200 + both-flags 422.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`,
`mypy --strict`.
