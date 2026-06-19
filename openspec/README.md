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
- `add-agent-supplied-summaries` — agent-driven L3 summarisation without a
  configured LLM backend: `collect_summary_jobs` / `apply_summary` on
  `DreamingEngine` (core); `summary_jobs` + `summary_put` MCP tools; `mintmory
  summary-jobs` + `mintmory summary-put` CLI commands; `GET /summaries/jobs` +
  `PUT /summaries/{concept}` HTTP routes. The agent calls `summary_jobs` to
  receive the pending concept work-list (same selection as `memory_dream`),
  writes each summary text itself, and stores it with `summary_put` — no
  `MINTMORY_LLM_*` backend required. `generate_summaries` is byte-for-byte
  equivalent after the shared selection helper refactor. (implementing)
- `add-image-understanding` — agent-supplied vision (G5): `image_jobs` /
  `image_caption_put` core functions + MCP tools + CLI commands + HTTP routes
  (`GET /images/jobs`, `PUT /images/{file_id}`); `index-tree --vision` flag for
  SVG inline extraction (pure stdlib) and raster queueing; `VisionProvider` /
  `VisionSettings` config (`MINTMORY_VISION_*`); `ImageJob` / `ImageDescription`
  types; `get_annotating_descriptions` + `find_image_file_record` storage helpers;
  `index_mode='vision'` CHECK widening (idempotent migration); optional `[image]`
  (Pillow downscale) / `[ocr]` (future tesseract) extras; `llm`/`ocr` are a
  compile-time seam that raises clearly in v1. No new required dependency; no model
  call in the agent path; no change to existing search/notes/index-tree paths.
  (implementing)
