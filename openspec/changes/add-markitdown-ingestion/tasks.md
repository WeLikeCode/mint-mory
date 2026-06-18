# Tasks — `add-markitdown-ingestion`

Disjoint file ownership so the work parallelises cleanly (one owner per file).

## 1. Core conversion module  — owns `packages/core/src/mintmory/core/conversion.py` (new)
- [x] 1.1 Implement the module per design §1–§3 (lazy markitdown import).
- [x] 1.2 `clean_markdown` conservative + idempotent; `extract_markdown` dispatch exact.

## 2. Config  — owns `packages/core/src/mintmory/core/config.py`
- [x] 2.1 Add `ConversionSettings` (`MINTMORY_CONVERT_*`) per design §4.
- [x] 2.2 Wire `convert: ConversionSettings` into `Settings`.

## 3. Packaging  — owns `packages/core/pyproject.toml`, `packages/cli/pyproject.toml`
- [x] 3.1 Add `docs` extra (`markitdown[all]`) to core.
- [x] 3.2 Add `docs` extra (`mintmory-core[docs]`) to cli.

## 4. CLI wiring  — owns `packages/cli/src/mintmory/cli/main.py`
- [x] 4.1 `ingest`: `--convert/--no-convert`, extended default glob, route via
      `extract_markdown`, graceful per-file skip, `converter` metadata, summary count.
- [x] 4.2 `doctor`: non-fatal `conversion` readiness row.

## 5. Core tests  — owns `packages/core/tests/test_conversion.py` (new)
- [x] 5.1 Cover `clean_markdown`, dispatch, fake-markitdown injection, size cap,
      `convert=False`, missing-markitdown error (design §7).

## 6. CLI tests  — owns `packages/cli/tests/test_cli.py`
- [x] 6.1 Convert-on-ingest (fake markitdown), graceful skip when absent, doctor row.

## 7. Docs  — owns `docs/hermes-onboarding.md`
- [x] 7.1 Note the `docs` extra + auto-conversion in the BULK LOAD / reference sections.

## 8. Gates & review (team-lead)
- [x] 8.1 `pytest` / `ruff check` / `ruff format --check` / `mypy` all green
      (352 passed, 1 skipped, 94.53% coverage).
- [x] 8.2 Adversarial review (6 lenses → verified triage; 8 confirmed / 12 rejected)
      → fixed every confirmed item:
      - [major] per-file conversion **timeout** (daemon thread, `MINTMORY_CONVERT_TIMEOUT_S`).
      - [major] **decompressed-output cap** vs zip/PDF bombs (`MINTMORY_CONVERT_MAX_OUTPUT_MB`).
      - [minor] wired `enabled` (global off-switch) — was dead config.
      - [minor] `failed` counter surfaced in the summary line.
      - [minor] `doctor` reports `len(CONVERTIBLE_SUFFIXES)` (18), not all 24 supported.
      - [minor] empty-conversion "produced no extractable text" note (not silently counted).
      - [minor] tests: assert `converter:"text"` metadata; assert doctor not-installed branch + hint.
- [ ] 8.3 Commit (ready; awaiting go-ahead).
