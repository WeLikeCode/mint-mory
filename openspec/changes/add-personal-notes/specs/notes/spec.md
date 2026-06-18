# Capability: notes (delta)

## ADDED Requirements

### Requirement: A note is an overlay on MemoryRecord
A note SHALL be an ordinary `MemoryRecord` distinguished by a first-class
`is_note` marker (`memories.is_note INTEGER NOT NULL DEFAULT 0`;
`MemoryRecord.is_note: bool = False`), NOT a new `MemoryCategory`. A note SHALL
carry one of the existing 8 categories. The `is_note` flag SHALL be the single
predicate that downstream behaviour (scoring, archival, contradiction, feedback,
listing) branches on — never `source` or `verified`. The column SHALL be added to
pre-existing databases by a best-effort, idempotent `ALTER TABLE` migration at
`initialise()` (PRAGMA `table_info` check + `try/except sqlite3.OperationalError`,
mirroring the trigram migration), so existing rows read back `is_note = False`.

#### Scenario: Existing memories are non-notes after migration
- **WHEN** a database created before this change is opened and `initialise()` runs
- **THEN** the `is_note` column is added with default 0 and every pre-existing
  memory reads back `is_note = False`, and a second `initialise()` is a no-op.

#### Scenario: A note round-trips with its flag and category
- **WHEN** a `MemoryRecord` with `is_note = True` and `category = preference` is
  added and re-fetched
- **THEN** the stored record has `is_note = True` and `category = preference`.

### Requirement: One capture primitive for user-authored notes
The system SHALL expose a single core primitive `create_note(adapter, content,
about=None, when=None, until=None, category=None, settings=None)` that creates a
`MemoryRecord` with `is_note=True`, `source=MemorySource.USER`, and
`verified=True`. The category SHALL default to `temporal` when `when` is given,
else `episodic`, and MAY be overridden. The salient date SHALL be stored in
`valid_from` and a deadline in `valid_until`. The system SHALL perform NO date
parsing: callers supply already-parsed ISO-8601 dates. `create_note` SHALL be
reachable through three thin transports — MCP `memory_note`, CLI `mintmory note`,
HTTP `POST /notes` — each of which serialises the same result.

#### Scenario: Free note defaults to episodic
- **WHEN** `create_note` is called with content only
- **THEN** the stored note has `is_note=True`, `source=user`, `verified=True`,
  and `category=episodic`.

#### Scenario: Dated note defaults to temporal and stores the date
- **WHEN** `create_note` is called with a `when` datetime
- **THEN** the stored note has `category=temporal` and `valid_from == when`.

#### Scenario: Capture guardrail is documented for the agent
- **WHEN** the MCP `memory_note` tool is described to an agent
- **THEN** its contract instructs the agent to call it ONLY on an explicit
  remember-this intent and to use `memory_add` for inferred facts.

### Requirement: Conservative optional anchoring via ANNOTATES
A note MAY be anchored to what it is "about" via a new asymmetric
`ConceptLinkType.ANNOTATES` edge (note → item; the note is always the
`source_memory_id`). `ANNOTATES` SHALL NOT be a member of `SYMMETRIC_LINK_TYPES`.
Anchor resolution SHALL be conservative: it creates a hard `ANNOTATES` link ONLY
when a single existing non-note, non-archived memory dominates the candidate pool
for the anchor phrase (top relevance share `>= anchor_min_dominance`); otherwise
it folds the anchor phrase's entities into the note's `entity_ids` (topic anchor)
and creates no link. In all cases the raw phrase SHALL be stored in
`metadata['anchor']`, and a hard link SHALL also set `metadata['anchor_memory_id']`.
Anchor candidate lookup SHALL NOT create a `QuerySession` or bump retrieval
counters. `create_note` SHALL return a `NoteResult` reporting `anchor_kind`
(`memory` | `topic` | `none`), `anchor_memory_id`, `anchor_entities`, and
`anchor_phrase`.

#### Scenario: Dominant match becomes a hard ANNOTATES link
- **WHEN** the anchor phrase matches one existing memory whose relevance share is
  at or above `anchor_min_dominance`
- **THEN** an `ANNOTATES` link from the note to that memory is created
  (`source=user`) and `NoteResult.anchor_kind == "memory"` with that memory's id.

#### Scenario: Ambiguous or absent match falls back to topic
- **WHEN** the anchor phrase has no dominant match (ambiguous results or empty
  store)
- **THEN** no link is created, the phrase's entities are folded into the note's
  `entity_ids`, `metadata['anchor']` holds the raw phrase, and
  `NoteResult.anchor_kind == "topic"`.

### Requirement: A notes listing surface with time views
The system SHALL expose `notes_list(adapter, about=None, upcoming=False,
overdue=False, limit=50, now=None)` returning `MemoryRecord` rows with
`is_note=True`. `upcoming` SHALL return notes with `valid_from > now` sorted
soonest-first; `overdue` SHALL return notes with `valid_from < now` that are not
archived; `about` SHALL filter to notes whose `entity_ids` contain the term
(case-insensitive) or whose `metadata['anchor']` contains it (case-insensitive
substring). With neither temporal flag, archived notes SHALL be excluded and
results ordered newest-first. Passing both `upcoming` and `overdue` SHALL raise a
validation error surfaced as a 4xx by transports. The surface SHALL be reachable
via MCP `notes_list`, CLI `mintmory notes [--about X] [--upcoming] [--overdue]`,
and HTTP `GET /notes`.

#### Scenario: Upcoming returns future-dated notes soonest-first
- **WHEN** `notes_list(upcoming=True)` is called
- **THEN** only notes with `valid_from` in the future are returned, ordered by
  `valid_from` ascending.

#### Scenario: Overdue excludes archived notes
- **WHEN** `notes_list(overdue=True)` is called and a past-due note has been
  archived ("done")
- **THEN** that archived note is not returned.

#### Scenario: Mutually-exclusive temporal flags are rejected
- **WHEN** `notes_list(upcoming=True, overdue=True)` is called
- **THEN** a validation error is raised (HTTP 422 / CLI bad-parameter).

### Requirement: A note can be marked done by archiving it
Marking a note done SHALL reuse the existing archival path (`is_archived=1`,
`is_active=0`) via the existing archive transports; no separate "done" primitive
is added. An archived note SHALL be excluded from `notes_list` (default), from
the search auto-include of annotating notes, and from note-authority contradiction
treatment.

#### Scenario: Archiving a note removes it from the notes surface
- **WHEN** a note is archived and `notes_list()` is called with default filters
- **THEN** the archived note is not returned.

### Requirement: Notes are configurable via MINTMORY_NOTE_*
The system SHALL provide a `NoteSettings` group (env prefix `MINTMORY_NOTE_`) with
`note_bonus` (default 0.05), `auto_include_cap` (default 3), and
`anchor_min_dominance` (default 0.6). Defaults SHALL be chosen so that no existing
non-note behaviour changes (the bonus applies only to `is_note` rows; auto-include
only adds `ANNOTATES`-linked notes).

#### Scenario: Defaults leave non-note behaviour unchanged
- **WHEN** `NoteSettings` is loaded with no environment overrides
- **THEN** `note_bonus=0.05`, `auto_include_cap=3`, `anchor_min_dominance=0.6`,
  and non-note memories are scored and archived exactly as before.
