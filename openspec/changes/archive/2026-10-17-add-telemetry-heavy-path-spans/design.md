# Design: heavy-path spans

## Decisions

- **`span()` gets its options here, not in part 3.** `typer.Exit` is a `RuntimeError` subclass (Typer 0.26.7), and in
  OpenTelemetry 1.42.1 `start_as_current_span` wraps the span in `use_span`, whose `except Exception` records an
  `exception` event and sets `Status(ERROR, "Exit: 0")`; `Span.set_status` keeps only an OK status, so it would also
  replace `mark_error`'s. Run on the locked versions: `typer.Exit(0)` through the defaults gives ERROR and one event,
  through `record_exception=False, set_status_on_exception=False` UNSET and none. `command_span` therefore needs the
  flags, and heavy-path runs before boundary-tracing. `kind`, `context` and `_NoopSpan.update_name` come along, so the
  signature changes once and boundary-tracing (which depends on this unit) only calls it.
- **`mintmory.index_tree.cochange` wraps the post-walk block only** (`if run_cochange and len(changed_docs) >= 2:`,
  i.e. `cluster_changesets` and `apply_changesets`). The walk-time per-file embeddings stay in `scan`, since they run
  file by file inside the walk. No span when fewer than two files changed or co-change is off (including the non-SQLite
  skip of `fix-cochange-tools-on-postgres`). A missing scikit-learn is an outcome (`unavailable`), not an error, since
  `index_tree` already catches `CoChangeUnavailable` and goes on.
- **The caption span goes around `captioner.describe(...)`**, the only inline caption call in `index_tree`
  (`cli/main.py`, raster branch, `captioner is not None`). With the default provider `agent` rasters are queued and no
  caption runs, so the scenario sets `MINTMORY_VISION_PROVIDER=llm` and stubs `llm.post_chat_completion` as the
  existing test `test_index_tree_vision_llm_mode_captions_raster_inline` does.
- **The privacy dream uses the real LLM path against a local test server**, not a fake summarizer, so the prompt
  (concept name, memory text) and the `Authorization` header really exist while telemetry is on. The threads scenario
  uses a fake summarizer because it checks trace ids, not content.
- **Existing spans are kept**: their attributes, read on `staging` and listed in the spec, carry no text.
