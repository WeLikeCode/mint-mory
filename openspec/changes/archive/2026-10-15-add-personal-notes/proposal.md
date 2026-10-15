# Change: Personal notes (user-authored memories, overlay on MemoryRecord)

**ID:** `add-personal-notes`
**Status:** proposed
**Capabilities:** `notes` (new), `search`, `dreaming`
**Owner:** orchestrator (Opus)

## Why

MintMory captures memories from three sources today — `agent`, `document`,
`inference` — and a user-ish `user` source that is otherwise indistinguishable
from agent-inferred rows. There is no first-class way for an agent to honour an
explicit **"remember this about X"** from the user: a deliberately-stated note
and a passively-inferred fact land in the same bucket, score the same way, are
archived by the same staleness rules, and lose to (or tie with) machine guesses
in contradiction resolution.

A user's explicit note is a higher-trust, higher-intent signal. It should:
surface a little earlier, ride along automatically when its subject is recalled,
never be silently archived as "stale", and **win** when it contradicts an
inferred or document-extracted memory. None of that is possible without marking
"this came from the user, on purpose" as a first-class property.

This change adds that property as a thin **overlay** on the existing
`MemoryRecord` — one boolean, one optional new link type, and the behaviour that
hangs off them — reusing `valid_from`/`valid_until`, `entity_ids`, and
`metadata` for everything else. It is deliberately small: a note is still an
ordinary memory in an ordinary category.

## What changes

1. **A note is an overlay, not a 9th category.** A note is a `MemoryRecord` with
   `source=user` + `verified=true` + a NEW first-class marker `is_note=true`. It
   still carries one of the existing 8 `MemoryCategory` values (a note can be a
   `fact`, `preference`, `identity`, …). One new column `memories.is_note INTEGER
   NOT NULL DEFAULT 0` and one new field `MemoryRecord.is_note: bool = False`,
   added via a **guarded `ALTER TABLE` migration** at `initialise()` using the
   same best-effort, introspection-then-add pattern as the trigram migration.

2. **One capture primitive, three thin transports.** A single core function
   `create_note(content, about?, when?, category?, ...)` is called by three thin
   wrappers: MCP `memory_note`, CLI `mintmory note`, HTTP `POST /notes`. The tool
   contract instructs the agent to call it **only on an explicit remember-this
   intent**; inferred facts keep using `memory_add`.

3. **Optional, conservative anchoring via a new `ANNOTATES` link type.** A note
   may be anchored to the thing it is "about" with a new
   `ConceptLinkType.ANNOTATES` edge (note → item, asymmetric, NOT symmetric).
   Anchor resolution is **conservative**: hard-link only on a confident/dominant
   match, otherwise fall back to *topic* anchoring (fold the anchor phrase's
   entities into the note's `entity_ids`, stash the raw phrase in
   `metadata.anchor`). Anchoring is optional on every note.

4. **Time is passive and agent-supplied.** The note's salient date goes in the
   existing `valid_from` (a deadline goes in `valid_until`). MintMory does **no**
   date parsing — the agent supplies an ISO-8601 date string (it owns the
   natural-language → date conversion), so **no new dependency** is added. Recall
   is time-*aware* (see §6) but **passive**: there are no active reminders or
   notifications (see "What this explicitly does NOT do").

5. **Retrieval respects notes.** (a) A small, **configurable** authority boost is
   added to `scoring.effective_score` when `is_note` (same scale as the recency
   bonus, default `0.05`) — a tie-breaker, not a hammer; it does **not** seed
   `usefulness_score`. (b) Search **auto-includes** the notes annotating each
   result (reverse-traversal of the `ANNOTATES` edge: result is the *target*),
   capped per anchor, surfaced via a new `SearchResponse.notes_on_results`.

6. **A notes surface.** A new core `notes_list(about?, upcoming?, overdue?,
   limit)` + transports (MCP `notes_list`, CLI `mintmory notes [--about X]
   [--upcoming] [--overdue]`, HTTP `GET /notes`). `upcoming` = notes with
   `valid_from > now` soonest-first; `overdue` = notes with `valid_from < now`
   not archived. Every returned record is tagged `is_note: true`.

7. **Dreaming protects and trusts notes.** Auto-archival queries gain `AND
   is_note = 0` (notes are **exempt** from staleness archival). In contradiction
   resolution a note **wins** over inferred/document memories (those are
   superseded/flagged); a note-vs-note conflict is **flagged for review**, never
   auto-resolved. A `stale` feedback vote on a note **flags it for review**
   instead of penalising it. Notes participate normally in concept-linking and
   may be summary inputs but are never replaced by a summary. A note can be
   marked **done → archived**.

8. **A new `MINTMORY_NOTE_*` config group.** `note_bonus` (default `0.05`),
   `auto_include_cap` (default `3`), and `anchor_min_dominance` (default `0.6`)
   live behind `NoteSettings` with defaults chosen so nothing about existing
   non-note behaviour changes.

## What this explicitly does NOT do

- **No active reminders / notifications / scheduling.** Time support is passive,
  recall-time only (`valid_from`/`valid_until` sorting + filtering). No cron, no
  push, no background watcher. (Deferred — may be a future change.)
- **No new `MemoryCategory`.** A note is an overlay flag; it cross-cuts the
  existing 8 categories.
- **No date parsing / NL-time dependency.** The agent supplies ISO dates;
  MintMory stores them. No `dateparser`/`dateutil` added.
- **No second store, no embedding/index change, no schema change beyond** the one
  `is_note` column and the one `ANNOTATES` link-type CHECK/enum value.
- **No change to default scoring/archival/contradiction behaviour for non-note
  rows.** Every new default reproduces today's behaviour where applicable.

## Impact

- **Core types/schema:** `core/types.py` (`MemoryRecord.is_note`,
  `ConceptLinkType.ANNOTATES`; `SearchResponse.notes_on_results`),
  `core/schema.sql` (`is_note` column + `ANNOTATES` in the `concept_links`
  CHECK), `core/storage.py` (`_MEMORY_COLUMNS`, `_memory_row_values`,
  `_row_to_memory`, guarded `_ensure_is_note_column` migration).
- **Capture/retrieval logic:** new `core/notes.py` (`create_note`, anchor
  resolution, `notes_list`); `core/storage.py` (`get_annotating_notes`,
  `list_notes`, `_passes_filter`/`search` auto-include hook);
  `core/scoring.py` (`effective_score` `note_bonus` param).
- **Dreaming:** `core/dreaming.py` (`archive_stale` `is_note=0` guard,
  contradiction authority rules); `core/storage.py` archival query guards.
- **Feedback:** `core/storage.py` `apply_feedback` (stale-on-note → flag).
- **Config:** `core/config.py` (`NoteSettings`, `MINTMORY_NOTE_*`).
- **Transports:** `packages/mcp` (`memory_note`, `notes_list`),
  `packages/cli` (`note`, `notes`), `packages/api` (`POST /notes`, `GET /notes`
  + request schema), `docs/openapi/mintmory.yaml`.
- **Tests:** core notes/storage/scoring/dreaming + each transport.
- **Docs:** `docs/EXPERIMENTS.md` (`MINTMORY_NOTE_*` knobs), README/agent docs.
- **Back-compat:** the migration is best-effort and idempotent (existing DBs gain
  `is_note` defaulting to 0 — every existing row is a non-note); `note_bonus`
  affects only `is_note=1` rows; all archival/contradiction changes only add
  constraints to or branch on the note flag. No existing behaviour changes for
  non-note memories. No data migration.
