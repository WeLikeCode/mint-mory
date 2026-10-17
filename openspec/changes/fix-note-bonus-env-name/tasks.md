# Tasks — fix-note-bonus-env-name

Paths: `config.py` = `packages/core/src/mintmory/core/config.py`, tests in
`packages/core/tests/test_config.py`. Line numbers are as of `staging` a08aee3.

## 1. Failing tests first
- [x] 1.1 In `test_config.py` add `class TestNoteSettingsEnvNames` (the file groups
  tests in classes; import `NoteSettings` and `load_settings` from
  `mintmory.core.config`). Every test takes `monkeypatch: pytest.MonkeyPatch`, starts
  with `monkeypatch.delenv("MINTMORY_NOTE_BONUS", raising=False)` and
  `monkeypatch.delenv("MINTMORY_NOTE_NOTE_BONUS", raising=False)`, then sets what
  its scenario needs with `monkeypatch.setenv`. Compare floats with
  `pytest.approx`. One test per scenario of `specs/notes/spec.md`:
  - `test_documented_name_sets_bonus` (fails today: 0.05)
  - `test_legacy_name_still_works` (passes today, guard)
  - `test_documented_name_wins_when_both_set` (fails today: 0.2)
  - `test_defaults_bounds_and_field_name_construction` (the `MINTMORY_NOTE_BONUS=5`
    part fails today: no error is raised)
  - `test_other_note_knobs_unaffected` (passes today, guard)
  Run `.venv/bin/pytest -q --no-cov packages/core/tests/test_config.py -k NoteSettingsEnvNames`.

## 2. Fix
- [ ] 2.1 `config.py` `NoteSettings` (:214-225): set
  `model_config = SettingsConfigDict(env_prefix="MINTMORY_NOTE_", extra="ignore", populate_by_name=True)`
  (`validate_by_name=True` is also acceptable on pydantic ≥ 2.11) and
  `note_bonus: float = Field(default=0.05, ge=0.0, le=1.0, validation_alias=AliasChoices("MINTMORY_NOTE_BONUS", "MINTMORY_NOTE_NOTE_BONUS"))`
  — documented name first (the first alias present wins), legacy second, same
  pattern as `StorageSettings.busy_timeout_ms` (:394-400). `AliasChoices` is already
  imported in `config.py`. Add a one-line comment naming both variables. Do not
  touch `auto_include_cap` or `anchor_min_dominance`.

## 3. Docs
- [ ] 3.1 `README.md:188`: keep `MINTMORY_NOTE_BONUS` and add "(legacy alias
  `MINTMORY_NOTE_NOTE_BONUS`)" to the Meaning column.
- [ ] 3.2 `docs/EXPERIMENTS.md:599`: change `MINTMORY_NOTE_NOTE_BONUS` to
  `MINTMORY_NOTE_BONUS` (mention the legacy alias in the Hypothesis cell or a
  footnote). Check with `git grep -n "MINTMORY_NOTE_NOTE_BONUS" -- README.md docs`
  that no doc names only the legacy variable.

## 4. Gates
- [ ] 4.1 `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate; the existing
  notes/search tests that build `NoteSettings(anchor_min_dominance=0.0)` or
  `StorageAdapter(":memory:", note_bonus=0.0)` pass unedited). These are the real gates of `.l4/config.yaml` (uv sync, ruff, mypy, pytest);
  OpenSpec validation is not a task gate (design.md `## Decisions`).
