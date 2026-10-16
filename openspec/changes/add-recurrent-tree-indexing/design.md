# Design: add-recurrent-tree-indexing (section 2, the online-only guard)

## Decisions

- **One counting rule for `text-skipped-online-only`.** The counter is evaluated once per
  scanned file in `index_tree` (`packages/cli/src/mintmory/cli/main.py`), right after
  `want_binary` and before the `store.manifest_get` unchanged check:
  `text_candidate and entry.online_only and not want_binary`. `want_binary` is
  `content and entry.suffix in ctypes and not budget_hit`, so it already folds in the
  download-budget cutoff: a file that the content pass would have read but the budget
  stopped is counted without any increment in the budget branch, and a file the content
  pass reads is not. Unchanged files are counted too. Reading the code (not a guess):
  `budget_hit` is set only after a read (`downloaded >= budget`), at the end of the
  previous file's iteration, so it is already true when the next file computes
  `want_binary`.
- **Supporting facts for the rule.** `_is_online_only(st: os.stat_result) -> bool` in `mintmory.core.tree_index` is called by `iter_dir_groups` once per file with the `fp.stat()` result only, so a test may replace it with a one-argument function. File records are `category='context'` memories (one per path, replaced in place); full-text chunks are `category='fact'`.
- **The budget scenario does not assume walk order.** `iter_dir_groups` uses `os.walk`
  `filenames` order, which is filesystem dependent. The scenario and its test assert
  one `content` and one `metadata` row, not which file is which.
- **Units that edit `index_tree` locate code by name, not line number** (`text_candidate`,
  `text_eligible`, `want_binary`, `desired_mode`, `store.manifest_get`), because
  `fix-cochange-tools-on-postgres` merges first and shifts lines. This is a working rule
  for the implementer, so it lives here and tasks.md, not as a requirement in the durable
  ingestion spec.
- **OpenSpec validation is not a task gate**, as in `deployment-hardening`; the gates are
  the Python ones in `.l4/config.yaml`.
