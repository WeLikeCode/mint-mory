# openspec/

Spec-driven change proposals for MintMory. Each change lives in
`changes/<id>/` with:

- `proposal.md` — why + what changes + impact
- `design.md` — the frozen interface contract implementers build against
- `tasks.md` — disjoint, ownable work items
- `specs/<capability>/spec.md` — requirement deltas (`ADDED`/`MODIFIED`/`REMOVED`)

A change is implemented against its `design.md`, reviewed adversarially, then its
`specs/` deltas describe the new behaviour of the named capability.

## Changes
- `leann-informed-tuning` — borrow from the LEANN analysis (adopt nothing):
  hub-aware concept-graph pruning, a pluggable `_vector_scores` seam, a re-embed
  guard regression test, and ADR-0006 (vector-scale strategy; never LEANN). (proposed)
- `add-trigram-substring-search` — FTS5 trigram tokenizer for true substring
  matching (`wall` → `firewall`) + N-way RRF fusion of porter-FTS/trigram/vector.
  (proposed)
- `improve-search-recall` — fix a search crash (NULL vector distance on
  mixed-dimension embeddings) + index text-file content + prefix/compound FTS
  matching + relevance normalisation. (IMPLEMENTED)
- `add-markitdown-ingestion` — auto-convert PDF/DOCX/XLSX/PPTX/… to Markdown via
  Microsoft markitdown during `mintmory ingest`. (implemented, MM-11)
- `add-recurrent-tree-indexing` — `mintmory index-tree`: online-only-aware
  indexing of a cloud folder for Hermes: metadata+context for every file, opt-in
  bounded full-text, incremental + `--force` re-index, manifest-backed. (IMPLEMENTED,
  manual cadence — see `results.md`; G5 image OCR + launchd recurrence are future)
- `add-personal-notes` — first-class user-authored notes (`is_note` flag on
  `MemoryRecord`): `memory_note` / `mintmory note` / `POST /notes` capture tools
  with a remember-this guardrail; conservative `ANNOTATES` hard-link anchoring to
  existing memories; note-authority contradiction resolution (note beats inferred,
  deterministic offline); auto-include of annotating notes on search results
  (`notes_on_results` channel); notes exempt from staleness auto-archival; "done"
  = explicit archive. Three new `MINTMORY_NOTE_*` knobs (bonus, cap, dominance).
  (proposed)
