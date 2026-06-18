# Live results — `add-recurrent-tree-indexing`

Run 2026-06-17 against
`/Users/you/Library/CloudStorage/OneDrive-SharedLibraries-ExampleOrg`
into the shared `~/.mintmory/hermes.db` (backed up first to
`hermes.db.bak-pre-index`).

## What was run + observed

| Step | Command (abridged) | Result |
|---|---|---|
| Smoke | `index-tree … --db /tmp/smoke.db --no-content --limit 200` | 200 files / 0.7s; 198 flagged online-only; **0 downloads** (du stayed 1.4M) |
| Full metadata | `index-tree … --no-content` | **15,258 files in 22s**, 0 downloads; hermes.db 420 → 15,678 |
| Incremental (a) | re-run `--no-content` | **15,258 unchanged, 0 new** — idempotent |
| Full-text (opt-in) | `--content --max-download-mb 20` (60s timeout) | downloaded 25.8 MB, **10 docs full-texted (186 chunks)**, 1 legacy `.doc` unsupported → skipped gracefully, budget enforced |
| Force (b) | `… --force --limit 30` on a subfolder | **8/8 updated, 0 unchanged**; prior versions archived |
| Search | `mintmory search "parking docker"` | 10 results, metadata + context returned |

## Issues found & fixed during the live test
- A literal CR in a string constant (`"Icon\r"`) broke mypy tokenization → rebuilt
  via `chr(13)`.
- Several lines >100 cols (ruff E501) → wrapped.
- mypy `no-any-return` in `manifest_get` and a test helper → explicit typing.
- A test matched `content LIKE '%a.md%'`, which also hit *sibling* records that
  list `a.md` → tightened to match by metadata `rel`.
- The doctor conversion-row test assumed markitdown absent; after installing the
  `docs` extra it failed → made it env-independent (monkeypatch both branches).

## Verified behaviours
- Online-only safe: metadata pass never downloads (stat-only walk).
- Budget overshoot is bounded: files larger than `max_file_mb` (25 MB) are rejected
  by the on-disk cap *before* any download, so a run can overshoot the download
  budget by at most one ≤25 MB file.
- Graceful per-file failure (unsupported `.doc`, timeouts) → skip + continue.

## Known follow-ups (not blocking)
- **`--force --no-content` downgrades** a previously full-texted doc back to
  metadata-only (it re-indexes per current flags). Intentional but worth a note;
  re-running with `--content` restores full text.
- **G5**: images/diagrams are metadata+context only (no OCR/vision yet).
- **Recurrence**: cadence=manual, so no launchd agent was installed. Re-run
  `mintmory index-tree … --content` (incremental) whenever you want a refresh.
- **markitdown** must be installed for the full-text pass (`uv sync --extra docs`);
  it was installed into the local venv for the live run. `uv.lock` already pins the
  `docs` deps, so no lock change was needed.
