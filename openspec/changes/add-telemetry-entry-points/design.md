# Design: entry points

## Decisions

- **No guard at the entry points; the failure policy is runtime's.** `add-telemetry-runtime` ("Telemetry init never
  raises") catches every init failure inside `init_telemetry`; a second `try/except` in four places would be a second
  copy of the policy. The scenario "A telemetry failure does not stop a command" pins the end-to-end result.
- **The CLI callback and the stdio servers pass no settings.** `load_settings()` validates every settings group and
  raises on, for example, `MINTMORY_SUMMARY_CONCURRENCY=0`; as the CLI callback runs before every command (and before
  `<cmd> --help`), calling it there would turn any bad unrelated variable into a failure of every command, help
  included. `mintmory-mcp` no longer fails at startup on such a variable; its tools load settings per call and report
  the error there, as `mintmory-history-mcp` already does.
- **`serve` and `mcp-serve` skip the CLI init**, so the API and MCP servers report their own service names.
- **The callback also runs for `mintmory <cmd> --help`** (Click calls the group callback before the subcommand parses
  `--help`; checked with Typer's `CliRunner`). In `auto` this costs at most one 100 ms probe; not worth special-casing.
