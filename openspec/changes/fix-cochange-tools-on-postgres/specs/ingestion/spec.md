# Capability: ingestion (delta)

## ADDED Requirements

### Requirement: Co-change CLI commands fail cleanly on other backends
When the CLI store is not a `SqliteBackend`, `mintmory docs timeline` and
`mintmory docs changed-with` SHALL print `COCHANGE_SQLITE_ONLY_MESSAGE` and exit
with code 1 instead of raising, and `mintmory index-tree` SHALL skip its co-change
pass with a one-line notice and otherwise finish normally (exit 0, report printed).
On a SQLite store nothing changes.

#### Scenario: docs commands on a non-SQLite store
- **GIVEN** `mintmory.cli.main._get_store` is monkeypatched to return a stub that wraps a real initialised SQLite store, forwards every attribute except `connect` (which raises `AttributeError`), and is not a `SqliteBackend` instance
- **WHEN** `mintmory docs timeline` and `mintmory docs changed-with /any/path` run
- **THEN** each exits with code 1, its output contains `co-change is SQLite-only`, and `result.exception` is not an `AttributeError`.

#### Scenario: index-tree on a non-SQLite store skips co-change
- **GIVEN** the same stub store and the two-burst tree of `test_index_tree_cochange_cli.py` (`_make_tree`), which yields change-sets on SQLite
- **WHEN** `mintmory index-tree <root> --cochange` runs
- **THEN** it exits 0, the output contains `co-change skipped` and `co-change is SQLite-only`, the report table is printed (it contains `scanned`) without a `changesets` row, and no stored document memory has a `changeset_id` in its metadata.

#### Scenario: SQLite behaviour is unchanged
- **WHEN** the existing tests in `packages/cli/tests/test_index_tree_cochange_cli.py` run against SQLite
- **THEN** they pass unedited.
