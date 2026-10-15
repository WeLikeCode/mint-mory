# dreaming Specification

## Purpose
TBD - created by archiving change leann-informed-tuning. Update Purpose after archive.

## Requirements

### Requirement: Hub-aware concept-graph pruning
The dreaming concept-linking step SHALL support giving high-degree "hub" concepts
a larger per-node link budget, so a uniform degree cap cannot sever the links that
keep a memory cluster connected. The behaviour SHALL be opt-in and default to the
existing uniform cap.

#### Scenario: Default reproduces the uniform cap
- **WHEN** `hub_cap_multiplier` is 1.0 (default)
- **THEN** the kept link set is identical to the prior uniform per-node cap.

#### Scenario: Hubs retain more links when enabled
- **WHEN** `hub_cap_multiplier > 1.0` and a concept's candidate-degree is at/above
  the `hub_degree_percentile` threshold
- **THEN** that hub concept may keep up to `int(max_per_node * hub_cap_multiplier)`
  links while non-hub concepts stay capped at `max_per_node`, deterministically.

### Requirement: Notes are exempt from auto-archival
The dreaming archival step and the anomaly-detection scan SHALL exclude notes:
archival/anomaly queries SHALL add `AND is_note = 0`. A note SHALL NEVER be
auto-archived by staleness, regardless of its `staleness_score`, `is_stale`, or
`last_accessed_at`. Notes SHALL also be excluded from the `never_accessed` and
`high_staleness_useful` anomaly lists. A note MAY still be archived explicitly
("done") via the archive path; that is separate from staleness archival.

#### Scenario: A stale-scored note is not auto-archived
- **WHEN** `archive_stale()` runs and a note has `is_stale=1`,
  `staleness_score >= ARCHIVE_THRESHOLD`, and an old/absent `last_accessed_at`
- **THEN** the note is not archived.

#### Scenario: Notes do not appear as staleness anomalies
- **WHEN** `detect_anomalies()` runs
- **THEN** no note id appears in `never_accessed` or `high_staleness_useful`.

### Requirement: Notes win contradictions over inferred memories
Contradiction resolution SHALL apply a deterministic note-authority pass that runs
even when no LLM `conflict_resolver` is configured (`provider=none`). When a
flagged note contradicts a non-note (inferred/document) memory, the non-note
memory SHALL be superseded (its `superseded_by` set to the note's id, marked
inactive and archived) and the note's review flag cleared. When two notes
contradict each other, BOTH SHALL remain `flagged_for_review` for human review and
neither SHALL be auto-resolved or superseded. Non-note-vs-non-note contradictions
SHALL continue to use the injected resolver unchanged. The note-authority pass
SHALL remain idempotent: a re-run makes no further change to already-resolved
pairs, and note-vs-note pairs stay flagged without drifting counts.

#### Scenario: A note supersedes a contradicting inferred memory
- **WHEN** a flagged note contradicts an inferred memory and `provider=none`
- **THEN** the inferred memory's `superseded_by` is set to the note's id, it is
  archived, the note's `flagged_for_review` is cleared, and the resolution counts
  toward `contradictions_resolved`.

#### Scenario: Note-vs-note conflicts are flagged, not auto-resolved
- **WHEN** two notes contradict each other
- **THEN** both remain `flagged_for_review`, neither is superseded, and the pair
  is not counted as resolved.

### Requirement: Stale feedback on a note flags it instead of penalising it
A `stale` feedback vote SHALL behave as today for non-note memories (increment
`staleness_score`, flip `is_stale` at the threshold). For a note, a `stale` vote
SHALL instead set `flagged_for_review = 1` and SHALL NOT change `staleness_score`
or `is_stale`. The `useful` feedback path SHALL be unchanged for notes (they may
still be reinforced). A note SHALL never be replaced by a summary; notes SHALL
otherwise participate normally in concept-linking and MAY be summary inputs.

#### Scenario: Stale vote on a note flags it for review
- **WHEN** `apply_feedback(note_id, useful=False, stale=True)` is called
- **THEN** the note's `flagged_for_review` becomes 1 while its `staleness_score`
  and `is_stale` are unchanged.

#### Scenario: Stale vote on a non-note is unchanged
- **WHEN** `apply_feedback(memory_id, useful=False, stale=True)` is called for a
  non-note memory
- **THEN** the behaviour is byte-identical to before this change.

### Requirement: Agent-supplied L3 concept summaries (BYO-LLM)
The dreaming engine SHALL support populating concept summaries from text supplied
by the active agent, as a provider-independent alternative to the configured-LLM
summary path. This SHALL NOT require a configured LLM backend: it MUST work with
`MINTMORY_LLM_PROVIDER=none` and with no injected `summarizer`. No new
`LLMProvider` value SHALL be introduced. The new path SHALL read and write the
SAME `MemorySummary` rows (keyed on `concept`) as the configured-LLM path.

The engine SHALL expose two methods:

- `collect_summary_jobs(include_all: bool = False) -> list[SummaryJob]` — returns
  the concepts the agent should summarise, selected by the SAME rules as
  `generate_summaries` (min-memories threshold, linking-stoplist drop, `top_k`
  cap, per-content `max_content_chars` truncation, `max_contents` cap). It SHALL
  NOT call any summarizer/LLM and SHALL NOT require one configured. By default
  (`include_all = False`) it SHALL return only concepts that NEED a (re)summary
  — those with NO current `MemorySummary` OR whose stored `memory_count` differs
  from the concept's current active count. With `include_all = True` it SHALL
  return one job per qualifying concept. Each `SummaryJob` SHALL carry the
  concept, the contributing memory ids, the (truncated/capped) contents, the full
  pre-cap active `memory_count`, and the existing summary text as
  `current_summary` (or `null`).
- `apply_summary(concept: str, summary_text: str) -> MemorySummary` — persists the
  agent's text for one concept, recomputing `memory_count` from the concept's
  current active count (the same definition the selection uses), with
  `is_current = true` and `generated_at = now`, via the existing
  `upsert_summary` (INSERT OR REPLACE by `concept`). It SHALL NOT call any
  summarizer/LLM. It SHALL store `summary_text` verbatim. It SHALL be idempotent:
  re-applying for the same concept overwrites the existing summary (preserving its
  row id).

A new `SummaryJob` model (`concept`, `memory_ids`, `contents`, `memory_count`,
`current_summary`) SHALL carry the prepare-step payload; it is transport data and
is NOT persisted.

#### Scenario: Jobs are produced with no LLM configured
- **WHEN** `collect_summary_jobs()` is called with `provider=none` and no injected
  summarizer, and the store has a concept with `>= min_memories` active memories
- **THEN** a `SummaryJob` for that concept is returned (its `contents`,
  `memory_ids`, and `memory_count` populated), and no LLM call is made.

#### Scenario: Default returns only concepts needing a (re)summary
- **WHEN** a concept already has a current `MemorySummary` whose `memory_count`
  equals its current active count
- **THEN** `collect_summary_jobs()` (default) omits that concept, while
  `collect_summary_jobs(include_all=True)` includes it.

#### Scenario: memory_count drift re-surfaces a concept
- **WHEN** a new active memory is added that increases a concept's active count
  above the count stored in its existing `MemorySummary`
- **THEN** `collect_summary_jobs()` (default) returns a job for that concept again.

#### Scenario: current_summary lets the agent refine
- **WHEN** a concept already has a `MemorySummary` and a job is returned for it
- **THEN** the job's `current_summary` equals the stored `summary_text`; for a
  concept with no summary, `current_summary` is `null`.

#### Scenario: apply_summary stores agent text idempotently
- **WHEN** `apply_summary(concept, "…")` is called (with `provider=none`)
- **THEN** a `MemorySummary` for `concept` is stored verbatim with `is_current =
  true` and `memory_count` equal to the concept's current active count; calling
  `apply_summary(concept, "…")` again overwrites it (the row id is preserved).

#### Scenario: applied summary clears the concept from the default job list
- **WHEN** `apply_summary(concept, "…")` is called and then
  `collect_summary_jobs()` (default) is called on the unchanged store
- **THEN** `concept` is NOT present in the returned jobs.

### Requirement: Agent-supplied summary transports
The agent-supplied summary methods SHALL be reachable through three thin
transports, each building the dreaming engine the same way `memory_dream` does
(`build_dreaming_engine` with the configured link/summary settings), so concept
selection follows `MINTMORY_SUMMARY_*` and the linking stoplist:

- MCP: `summary_jobs(include_all: bool = False, limit: int = 0) -> list[dict]` and
  `summary_put(concept: str, summary_text: str) -> dict`. `limit = 0` means no
  cap and is applied AFTER selection. The FastMCP `instructions` SHALL mention the
  agent-supplied summary loop and that no separate LLM backend is required.
- CLI: `mintmory summary-jobs` (rich table by default, `--json` for JSON,
  `--all/--needed`, `--limit`) and `mintmory summary-put <concept> [text]` (text
  from the positional argument, else `--file`, else stdin; empty text rejected).
- HTTP: `GET /summaries/jobs` (query `include_all`, `limit`; → `list[SummaryJob]`)
  and `PUT /summaries/{concept}` (body `{ "summary_text": "…" }` →
  `MemorySummary`). `docs/openapi/mintmory.yaml` SHALL define both paths and the
  `SummaryJob` / `SummaryPut` schemas.

The existing summary READ endpoints/tools (MCP `summary_list` / `summary_get`,
HTTP `GET /summaries` / `GET /summaries/{concept}`) SHALL be unchanged.

#### Scenario: MCP put then read round-trip
- **WHEN** `summary_put("oauth", "…")` is called over MCP and then
  `summary_get("oauth")`
- **THEN** `summary_get` returns the stored summary with the supplied text.

#### Scenario: GET /summaries/jobs is not shadowed by {concept}
- **WHEN** a client calls `GET /summaries/jobs`
- **THEN** it receives the jobs list (200) from the jobs handler, not a 404 from
  the `GET /summaries/{concept}` handler.

#### Scenario: CLI summary-put reads text from stdin
- **WHEN** `mintmory summary-put oauth` is run with the summary text piped on
  stdin (no positional text, no `--file`)
- **THEN** the piped text is stored as the `oauth` summary.

### Requirement: L3 concept summaries are generated for well-evidenced concepts
The dreaming summary step (`generate_summaries`) SHALL, for each entity appearing
in at least `summary_settings.min_memories` active, non-archived memories (after
dropping linking-stoplist concepts; honouring `top_k` selection and
`max_content_chars` / `max_contents` preparation), call the injected summarizer
over the prepared contents and upsert a `MemorySummary` per concept, idempotently
(an unchanged database yields 0 on a re-run). When no summarizer is configured the
step SHALL return 0 and write nothing.

The concept-selection and content-preparation logic SHALL be factored into ONE
shared private helper that BOTH `generate_summaries` and `collect_summary_jobs`
call, so the two paths select identical concepts and identical truncated/capped
contents for the same database and settings. This refactor SHALL NOT change
`generate_summaries`' observable behaviour: it MUST remain byte-for-byte
equivalent (the existing dreaming summary tests pass without modification).

#### Scenario: Refactor preserves generate_summaries behaviour
- **WHEN** `generate_summaries` runs after the selection logic is extracted into
  the shared helper
- **THEN** the concepts summarised, the `memory_count` recorded per concept, the
  idempotency behaviour, and the returned count are identical to before the
  refactor (the existing summary tests pass unedited).

#### Scenario: collect_summary_jobs selects the same concepts as generate_summaries
- **WHEN** `collect_summary_jobs(include_all=True)` and a configured-LLM
  `generate_summaries` run against the same database and settings
- **THEN** the set of concepts is identical, and each job's `contents` equals the
  contents that would be passed to the summarizer for that concept.
