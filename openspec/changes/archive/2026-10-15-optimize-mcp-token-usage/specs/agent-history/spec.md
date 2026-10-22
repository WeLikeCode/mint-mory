# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Concise history result projection
The `history_timeline` and `history_search` MCP tools SHALL accept a `verbosity`
parameter with values `"full"` and `"concise"`, defaulting to `"full"`. With
`"full"` they SHALL return exactly the current 15-field row shape, preserving
backward compatibility. With `"concise"` each returned row SHALL be reduced to at
least `date`, `repo`, `kind`, `title`, and a `snippet` (the row `summary` truncated
to ~200 characters), omitting the bulkier fields (such as `ts_start`, `branch`,
`agent`, `collection`, `source_path`, `segment_count`, `turn_lo`, `turn_hi`, and the
full `summary`). The concise projection SHALL be applied at the MCP layer only and
SHALL NOT change the shared query row shape used by the CLI.

#### Scenario: Concise timeline rows are reduced
- **GIVEN** an agent-history DB with session summaries in the window
- **WHEN** `history_timeline` is called with `verbosity="concise"`
- **THEN** each row contains `date`, `repo`, `kind`, `title`, and a `snippet`, does NOT contain `branch`/`ts_start`/`segment_count`/`turn_lo`/`turn_hi`/`source_path`/full `summary`, and the rows remain newest-first.

#### Scenario: Full verbosity and CLI output are unchanged
- **WHEN** `history_timeline` or `history_search` is called with the default `verbosity="full"`
- **THEN** the returned rows are byte-identical to the pre-change 15-field shape
- **AND** the `mintmory history` CLI output (which shares the underlying query) is unchanged regardless of the MCP verbosity.
