# Capability: notes (delta)

## ADDED Requirements

### Requirement: Note bonus is read from the documented MINTMORY_NOTE_BONUS
`NoteSettings.note_bonus` SHALL be read from `MINTMORY_NOTE_BONUS`, the documented
name, and from `MINTMORY_NOTE_NOTE_BONUS`, kept as a backward-compatible alias; when
both are set, `MINTMORY_NOTE_BONUS` SHALL win. The 0.0–1.0 bounds SHALL apply to
either name, `NoteSettings(note_bonus=...)` SHALL keep working, and README and docs
SHALL name `MINTMORY_NOTE_BONUS`.

#### Scenario: The documented name sets the bonus
- **GIVEN** `MINTMORY_NOTE_BONUS=0.1` and `MINTMORY_NOTE_NOTE_BONUS` unset
- **WHEN** `NoteSettings()` and `load_settings()` are built
- **THEN** `NoteSettings().note_bonus == 0.1` and `load_settings().note.note_bonus == 0.1` (today both are `0.05`).

#### Scenario: The legacy name still works
- **GIVEN** `MINTMORY_NOTE_NOTE_BONUS=0.2` and `MINTMORY_NOTE_BONUS` unset
- **WHEN** `NoteSettings()` is built
- **THEN** `note_bonus == 0.2`.

#### Scenario: The documented name wins when both are set
- **GIVEN** `MINTMORY_NOTE_BONUS=0.1` and `MINTMORY_NOTE_NOTE_BONUS=0.2`
- **WHEN** `NoteSettings()` is built
- **THEN** `note_bonus == 0.1`.

#### Scenario: Defaults, bounds and construction by field name
- **WHEN** neither variable is set, `NoteSettings().note_bonus == 0.05`; **AND WHEN** `MINTMORY_NOTE_BONUS=5` (or `MINTMORY_NOTE_NOTE_BONUS=5`) is set
- **THEN** building `NoteSettings()` raises `pydantic.ValidationError`; and with neither variable set, `NoteSettings(note_bonus=0.7).note_bonus == 0.7`.

#### Scenario: The other note knobs are unaffected
- **GIVEN** `MINTMORY_NOTE_AUTO_INCLUDE_CAP=5` and `MINTMORY_NOTE_ANCHOR_MIN_DOMINANCE=0.8`
- **WHEN** `NoteSettings()` is built
- **THEN** `auto_include_cap == 5` and `anchor_min_dominance == 0.8`, and `NoteSettings(anchor_min_dominance=0.0).anchor_min_dominance == 0.0`.
