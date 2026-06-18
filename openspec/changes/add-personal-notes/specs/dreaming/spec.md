# Capability: dreaming (delta)

## ADDED Requirements

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

## MODIFIED Requirements

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
