# Tasks — `add-personal-notes`

Disjoint file ownership so parallel Sonnet agents do not collide. Groups 1–4
touch **core** files; to avoid two agents editing the same file, the core work is
split by file: **Group 1 owns `types.py` + `schema.sql`**, **Group 2 owns
`storage.py` (CRUD/migration/columns) + `scoring.py`**, **Group 3 owns the new
`notes.py`**, **Group 4 owns `dreaming.py`**, **Group 5 owns `config.py`**.
`storage.py` is touched ONLY by Group 2 (it also adds the storage methods Groups
3/4 call); Groups 3/4 must treat the Group-2 storage signatures in design.md as
fixed and call them, not edit storage.py. Run Group 1 + Group 5 first (pure
additions other groups import), then 2, then 3/4 in parallel, then 6, then 7/8.

## 1. Core types + schema — owns `core/types.py`, `core/schema.sql`
- [x] 1.1 Add `MemoryRecord.is_note: bool = False` (design §1a).
- [x] 1.2 Add `ConceptLinkType.ANNOTATES = "annotates"`; do NOT add to
      `SYMMETRIC_LINK_TYPES`; update the "11 typed" docstring → 12 (design §1b).
- [x] 1.3 Add `SearchResponse.notes_on_results: dict[str, list[MemoryRecord]] =
      Field(default_factory=dict)` (design §1c).
- [x] 1.4 Add `NoteResult` model (note + anchor_kind + anchor_memory_id +
      anchor_entities + anchor_phrase) (design §4c).
- [x] 1.5 schema.sql: add `is_note INTEGER NOT NULL DEFAULT 0` to `memories` +
      `idx_memories_note` partial index; add `'annotates'` to the `concept_links`
      `link_type` CHECK (design §1d, §1e).

## 2. Storage CRUD + migration + scoring — owns `core/storage.py`, `core/scoring.py`
- [x] 2.1 `scoring.effective_score`: add `is_note: bool = False`,
      `note_bonus: float = 0.0` params (+ `NOTE_BONUS=0.05` constant), additive
      bonus only when `is_note`; default 0.0 reproduces today (design §3).
- [x] 2.2 Column sync: add `"is_note"` to `_MEMORY_COLUMNS` (append after
      `contradicts_ids`), `_memory_row_values` (`_bool(record.is_note)`),
      `_row_to_memory` (`is_note=bool(row["is_note"])`), and `update_memory`
      sets/params — keep all four lists in lockstep (design §1g).
- [x] 2.3 `_ensure_is_note_column(conn)` guarded ALTER TABLE; call from
      `initialise()` after `_ensure_trigram` (design §1f).
- [x] 2.4 `__init__`: add `note_bonus: float | None = None` +
      `auto_include_cap: int | None = None`, lazy-default from `NoteSettings`;
      store `self._note_bonus` / `self._auto_include_cap` (design §5a, §5b).
- [x] 2.5 `search()`: pass `is_note`/`note_bonus` to `effective_score`; add the
      Phase-3 reverse-ANNOTATES auto-include into `notes_on_results` (separate
      channel; no `primary`/`total_found`/lineage/retrieval impact) (design §5a, §5b).
- [x] 2.6 `get_annotating_notes(memory_id, cap)` reverse-traversal helper (design §5b).
- [x] 2.7 `list_notes(...)` (is_note=1; upcoming/overdue/entity/anchor filters +
      ordering) (design §5c).
- [x] 2.8 `apply_feedback`: stale-vote on a note → `flagged_for_review`, no
      staleness penalty; non-note path unchanged (design §5d).
- [x] 2.9 `supersede_memory(memory_id, by_id)` helper (design §6b).
- [x] 2.10 `get_never_accessed_stale` / `get_high_staleness_useful`: add
      `AND is_note = 0` (design §5e).

## 3. Notes module — owns `core/notes.py` (NEW)
- [x] 3.1 `create_note(...)`: defaults (temporal/episodic), persist via
      `add_memory`, anchor resolution, single follow-up `update_memory`, return
      `NoteResult` (design §4a).
- [x] 3.2 `_resolve_anchor(...)` + `_anchor_candidates` usage: conservative
      dominance test → ANNOTATES hard-link (LinkSource.USER, strength 1.0) else
      topic fold; always stash `metadata['anchor']` (design §4b). (Calls the
      Group-2 storage helper `_anchor_candidates`; if Group 2 has not landed it
      yet, depend on the design signature.)
- [x] 3.3 `notes_list(...)`: both-flags ⇒ ValueError; delegate to
      `adapter.list_notes` (design §4d).

> Group 2 must add `_anchor_candidates(self, about, limit=5)` to storage.py
> (design §4b) — listed here for visibility; OWNED by Group 2.

## 4. Dreaming — owns `core/dreaming.py`
- [x] 4.1 `archive_stale()`: add `AND is_note = 0` (design §6a).
- [x] 4.2 `detect_anomalies()`: add `AND is_note = 0` to never_accessed +
      high_staleness_useful queries (design §6a).
- [x] 4.3 `resolve_contradictions()`: deterministic note-authority pass (note >
      inferred/document supersede; note-vs-note flag-only; relax the
      `resolver is None` early-return so authority runs offline; non-note pairs
      still use the injected resolver) (design §6b).
- [x] 4.4 Add the "note never replaced by a summary / never auto-stale" invariant
      comments in `generate_summaries`/`rehabilitate` (no behaviour change) (design §6c, §6a).

## 5. Config — owns `core/config.py`
- [x] 5.1 `NoteSettings` (`MINTMORY_NOTE_*`): `note_bonus=0.05`,
      `auto_include_cap=3`, `anchor_min_dominance=0.6`; register `note` on
      `Settings` (design §2).

## 6. Transports — split by package (no overlap)
### 6a. MCP — owns `packages/mcp/src/mintmory/mcp/server.py`
- [x] 6a.1 `memory_note` tool with the remember-this guardrail; ISO parse →
      error dict on failure (design §8a).
- [x] 6a.2 `notes_list` tool; both-flags → error dict (design §8a).
- [x] 6a.3 Bump `instructions` ("12 typed … incl. annotates" + memory_note note).

### 6b. CLI — owns `packages/cli/src/mintmory/cli/main.py`
- [x] 6b.1 `_parse_iso` helper; `note` command (anchor-aware output) (design §8b).
- [x] 6b.2 `notes` command (`--about/--upcoming/--overdue/--limit`, rich table)
      (design §8b).

### 6c. HTTP API — owns `packages/api/src/mintmory/api/{schemas.py,app.py}` +
`docs/openapi/mintmory.yaml`
- [x] 6c.1 `NoteCreate` schema (design §8c).
- [x] 6c.2 `POST /notes` (→ `NoteResult`) + `GET /notes` (→ `list[MemoryRecord]`,
      both-flags 422) routes; import `NoteResult` (design §8c).
- [x] 6c.3 OpenAPI YAML: add `is_note`, `annotates`, `NoteCreate`, `NoteResult`,
      and the two paths.

## 7. Tests — owns the `tests/` trees (per package; disjoint from impl groups)
- [x] 7.1 core: `test_schema.py`/`test_storage.py` migration + column round-trip +
      annotates link; new `test_notes.py` (create/anchor/list); `test_scoring.py`
      note_bonus; `test_search.py` auto-include + note ranking; `test_dreaming.py`
      archival-exempt + authority; feedback stale-on-note (design §10).
- [x] 7.2 mcp: `memory_note`/`notes_list` happy + bad-ISO (design §10).
- [x] 7.3 cli: `note`/`notes` via typer runner incl. time views + bad date.
- [x] 7.4 api: `POST /notes` 201, `GET /notes` 200, both-flags 422.

## 8. Docs — owns `docs/EXPERIMENTS.md`, `README*`, agent/onboarding docs,
`openspec/README.md`
- [x] 8.1 `docs/EXPERIMENTS.md`: `MINTMORY_NOTE_*` knob entries (note_bonus,
      auto_include_cap, anchor_min_dominance; defaults + what to measure).
- [x] 8.2 README / agent doc: "personal notes" section (capture guardrail, time
      semantics, anchoring, done=archive).
- [x] 8.3 `openspec/README.md`: add the `add-personal-notes` bullet.

## 9. Review & integration (orchestrator, Opus)
- [x] 9.1 Verify gates per package (pytest cov ≥ 80 / ruff / ruff format / mypy --strict).
- [x] 9.2 Independent Opus reviewer: conformance to design.md + the §9 invariants
      (non-note ranking byte-identical at note_bonus=0.0; ANNOTATES reverse-only;
      migration idempotent/best-effort; authority deterministic offline).
- [x] 9.3 Orchestrator applies fixes, re-runs gates, commits.
