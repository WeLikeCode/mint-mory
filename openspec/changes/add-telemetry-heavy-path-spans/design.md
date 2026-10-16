# Design: heavy-path spans

## Decisions

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
