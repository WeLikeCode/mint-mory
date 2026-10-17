# Change: The documented note-bonus variable works

## Why

`README.md:188` documents `MINTMORY_NOTE_BONUS` (ranking boost for user notes,
default `0.05`). The code reads a different name: `NoteSettings`
(`packages/core/src/mintmory/core/config.py:214-225`) has
`env_prefix="MINTMORY_NOTE_"` and the field `note_bonus`, so pydantic-settings looks
for `MINTMORY_NOTE_NOTE_BONUS`; `extra="ignore"` silently drops
`MINTMORY_NOTE_BONUS`. A user who follows the README changes nothing.
`docs/EXPERIMENTS.md:599` documents the name the code reads.

## What changes

- `note_bonus` accepts both names through
  `validation_alias=AliasChoices("MINTMORY_NOTE_BONUS", "MINTMORY_NOTE_NOTE_BONUS")`.
  The documented name is listed first, so it wins when both are set (verified with
  pydantic 2.13.4 / pydantic-settings 2.14.1 from `uv.lock`: the first alias that is
  present wins). The old name stays as a backward-compatible alias.
- `NoteSettings.model_config` gains `populate_by_name=True`. Without it, setting a
  `validation_alias` makes `NoteSettings(note_bonus=0.7)` silently return the default
  `0.05` (verified), which would break construction by field name.
- `StorageSettings.busy_timeout_ms` (`config.py:394-400`) already uses this
  `AliasChoices` pattern for a renamed variable.
- Docs name `MINTMORY_NOTE_BONUS` (README keeps it and mentions the legacy alias;
  `docs/EXPERIMENTS.md:599` is corrected).

`auto_include_cap` (`MINTMORY_NOTE_AUTO_INCLUDE_CAP`) and `anchor_min_dominance`
(`MINTMORY_NOTE_ANCHOR_MIN_DOMINANCE`) keep their names.

## Impact

- Affected specs: **notes** (ADDED).
- Code: `packages/core/src/mintmory/core/config.py` (`NoteSettings`). Docs:
  `README.md:188`, `docs/EXPERIMENTS.md:599`. Tests:
  `packages/core/tests/test_config.py`.
- Default behaviour (no variable set) is unchanged: `note_bonus == 0.05`.
