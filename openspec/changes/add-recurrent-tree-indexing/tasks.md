# Tasks — add-recurrent-tree-indexing

Paths: `cli/main.py` = `packages/cli/src/mintmory/cli/main.py`, `tree_index.py` =
`packages/core/src/mintmory/core/tree_index.py`. Line numbers are as of `staging`
a08aee3.

## 1. Already implemented (on staging)
- [x] 1.1 Stat-only walk with online-only detection — `tree_index.py` (`_is_online_only` :117, `iter_dir_groups` :127); tests `packages/core/tests/test_tree_index.py:53-93`.
- [x] 1.2 Metadata + folder-context file records with a bounded sibling sample — `tree_index.py` (`render_file_record` :203); tests `test_tree_index.py:109-138`.
- [x] 1.3 Per-path manifest — `packages/core/src/mintmory/core/schema.sql:136-149` (`index_manifest`) and `packages/core/src/mintmory/core/storage.py:630-697` (`manifest_get/upsert/paths/delete`).
- [x] 1.4 `mintmory index-tree`: skip unchanged, replace changed in place, `--force`, `--prune` — `cli/main.py` (`index_tree` :454, unchanged check :648-660, replace :832-834, prune :874-881); tests `packages/cli/tests/test_cli.py:594-695`.
- [x] 1.5 Opt-in binary content pass bounded by `--max-download-mb` and `--content-types` — `cli/main.py:470-479` (options) and :688-724 (budget); verified live in `results.md` (no automated budget-cutoff test).
- [x] 1.6 Include/exclude globs and the collection tag; artifacts excluded only through `--exclude` (no default denylist) — `cli/main.py:542-543`, `tree_index.py:24-28`; tests `test_tree_index.py:65-91`, `test_cli.py:657-676`.
- [x] 1.7 Inline text-content pass for small plain-text files, on by default (added by improve-search-recall) — `cli/main.py:462-469` and :613-617; tests `test_cli.py:698-729`.

## 2. Online-only guard for the default text-content pass

The text-content pass reads every small `.md/.markdown/.txt/.text/.rst/.log` file
with no `online_only` check (`cli/main.py:613-617`), so a default run over a OneDrive
Files-On-Demand tree downloads every such placeholder. Owner decision: skip them by
default. A user who wants them can still run `--content --content-types txt,md`
(budgeted download).

- [ ] 2.1 Failing tests first, in `packages/cli/tests/test_cli.py` (next to
  `test_index_tree_text_content_indexed_by_default`, using the existing `cli_db`
  fixture, `runner`, `app` and `_store` helpers). A real file system cannot produce
  `st_blocks == 0`, so mark a file online-only with
  `monkeypatch.setattr("mintmory.core.tree_index._is_online_only", lambda st: st.st_size == cloud_size)`
  (the walk looks the function up in its module at call time; give `local.txt` and
  `cloud.txt` different sizes). To prove `cloud.txt` is never read, wrap
  `mintmory.core.conversion.extract_markdown` with
  `monkeypatch.setattr("mintmory.core.conversion.extract_markdown", spy)` where
  `def spy(path: str | Path, **kwargs: Any) -> Any:` records `Path(path).name` and
  returns `original(path, **kwargs)` (keep `original` from
  `mintmory.core.conversion.extract_markdown` before patching; `index_tree` imports
  `extract_markdown` inside the function, so the patch takes effect; `mypy packages`
  checks the tests too, so annotate the spy and import `Any`). Find a report
  row with `next(ln for ln in result.output.splitlines() if "text-skipped-online-only" in ln)`
  and check its value, as `test_index_tree_vision_svg_described_raster_queued_proprietary_skipped` does.
  - `test_index_tree_text_content_skips_online_only_file`: scenario "An online-only
    text file is not read by default" (spy never saw `cloud.txt`, saw `local.txt`;
    manifest rows read with `SELECT path, index_mode, online_only FROM index_manifest`).
  - `test_index_tree_online_only_skip_counted_per_run`: scenario "The count is per
    run and the row is shown only when non-zero" (second run shows `1` again; a tree
    with no online-only file, and a run with `--no-text-content`, have no
    `text-skipped-online-only` in `result.output`).
  - `test_index_tree_content_pass_reads_online_only_text_on_request`: scenario "The
    budgeted content pass can still fetch it on request" (`--content
    --content-types txt`; `cloud.txt` manifest `index_mode == "content"`; no
    `text-skipped-online-only` row).
  Run `.venv/bin/pytest -q --no-cov packages/cli/tests/test_cli.py -k online_only`;
  the first two must fail before 2.2.
- [ ] 2.2 The guard, in `index_tree` (`cli/main.py:613-617`): split the eligibility
  into `text_candidate = text_content and entry.suffix in TEXT_SUFFIXES and
  (text_max_bytes is None or entry.size <= text_max_bytes)` and
  `text_eligible = text_candidate and not entry.online_only`. Leave `want_binary`,
  `do_content`, the vision branch and the budget logic unchanged. Nothing else reads
  an online-only file on the default path.
- [ ] 2.3 The report counter: add `text_skipped_online_only = 0` next to the other
  counters (around `cli/main.py:584-591`); after `want_binary` is computed, do
  `if text_candidate and entry.online_only and not want_binary: text_skipped_online_only += 1`
  (this runs before the unchanged check, so the count is per scanned file); after
  the `base_rows` loop add
  `if text_skipped_online_only: table.add_row("text-skipped-online-only", str(text_skipped_online_only))`.
  Update the `--text-content` help text and the `index_tree` docstring to say
  online-only files are skipped by this pass.
- [ ] 2.4 Gates: `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate), and
  `npx --yes @fission-ai/openspec@1.14.1 validate add-recurrent-tree-indexing --strict`.
