# Change: a telemetry runtime that is on when a collector is there and never blocks MintMory (OpenTelemetry, part 1 of 4)

## Why

On `staging` the default `console` exporter writes to stdout (the `mintmory-mcp` stdio stream); with no collector the
OTLP exporter retries for 10 s, floods the logs and stalls exits; telemetry is off unless forced; the resource has only
`service.name`; tests cannot capture spans.

## What changes

See `specs/`. This unit also fixes the decisions parts 1b, 2, 3 and 4 share: `mark_error`, the init failure policy,
`none` per signal, single injection, and the root `conftest.py` test fixtures (see `design.md`). Wiring each entry
point is `add-telemetry-entry-points`.

## Impact

`telemetry.py`, `config.py` (`OTelSettings`), the root `conftest.py`, the two existing telemetry tests named in
tasks 7.1-7.2. With no collector and no configuration the shim stays a no-op as today; with one on `localhost:4318`,
MintMory exports.
