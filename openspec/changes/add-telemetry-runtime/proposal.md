# Change: a telemetry runtime that is on when a collector is there and never blocks MintMory (OpenTelemetry, part 1 of 4)

## Why

On `staging` (`packages/core/src/mintmory/core/telemetry.py`): the CLI and `mintmory-history-mcp` never initialise
telemetry; the default `console` exporter writes to stdout, the `mintmory-mcp` stdio stream; with no collector the
OTLP exporter retries for 10 s and floods the logs, and the SDK's exit hook stalls short commands; telemetry is off
unless forced, even with a collector on the standard port; the resource has only `service.name`; tests cannot capture
spans.

## What changes

See `specs/`: enablement modes (`auto` default), OTLP/HTTP by default with per-signal standard variables and console
on stderr, non-blocking export with failures logged once, a bounded `atexit` shutdown, the resource and sampler from
the standard environment, MintMory's providers made global (FastMCP's tool spans then reach the same exporters), a test seam, and the root
`conftest.py` pinning the existing suite to `MINTMORY_OTEL_ENABLED=false`. Wiring each entry point is
`add-telemetry-entry-points`.

## Non-goals

OTLP logs, gRPC, database-driver spans, new dependencies, new spans or metrics (parts 2 and 3).

## Impact

`telemetry.py`, `config.py` (`OTelSettings`), the root `conftest.py`, and the API telemetry test named in the tasks. With no collector and no configuration
the shim stays a no-op, as today (only the default values of `enabled` and `exporter` change); with a collector on `localhost:4318`, MintMory exports without configuration.
