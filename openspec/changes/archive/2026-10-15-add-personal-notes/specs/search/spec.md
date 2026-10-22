# Capability: search (delta)

## ADDED Requirements

### Requirement: Configurable authority boost for notes
Hybrid search SHALL add a small, configurable authority boost to the
`effective_score` of `is_note` rows, on the same additive scale as the recency
bonus (default `note_bonus = 0.05` from `NoteSettings`). The boost SHALL be a flat
addend applied at scoring time only and SHALL NOT seed `usefulness_score`. The
`note_bonus` parameter of `scoring.effective_score` SHALL default to `0.0` so that
the function and every existing caller behave exactly as before when notes are not
configured; a value of `0.0` SHALL reproduce today's ranking for all rows.

#### Scenario: A note outranks an equally-relevant non-note
- **WHEN** a note and a non-note memory have equal base relevance, usefulness,
  staleness, and recency, and `note_bonus > 0`
- **THEN** the note ranks ahead of the non-note.

#### Scenario: Zero bonus reproduces today's ranking
- **WHEN** `note_bonus = 0.0`
- **THEN** search returns results in the exact order produced before this change,
  for both note and non-note rows.

### Requirement: Auto-include the notes annotating each result
Search SHALL auto-include, for each primary result, the notes that ANNOTATE it,
found by a REVERSE traversal of the asymmetric `ANNOTATES` edge (the result is the
`target_memory_id`; the annotating note is the `source_memory_id`). The included
notes SHALL be capped per result by `auto_include_cap` (default 3; `0` disables),
ordered by link strength then recency, and SHALL exclude archived notes. They
SHALL be returned on a separate channel `SearchResponse.notes_on_results`
(`{result_id: [note records]}`) and SHALL NOT be merged into `memories`, counted
in `total_found`, recorded as `query_results`, or bump retrieval counters.

#### Scenario: Annotating notes ride along with their subject
- **WHEN** a result memory has notes linked to it via `ANNOTATES`
- **THEN** up to `auto_include_cap` of those notes appear under
  `notes_on_results[result_id]`, while `total_found` counts only the primary
  results.

#### Scenario: Traversal direction is reverse-only
- **WHEN** a primary result is itself the SOURCE of an `ANNOTATES` link (it
  annotates something else) but nothing annotates it
- **THEN** no notes are auto-included for that result (forward edges are not
  followed by the auto-include).

#### Scenario: Auto-include can be disabled
- **WHEN** `auto_include_cap = 0`
- **THEN** `notes_on_results` is empty and search behaves as before.
