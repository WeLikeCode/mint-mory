# Local observability stack

An OpenTelemetry Collector with Jaeger (traces) and Prometheus (metrics) for
looking at MintMory telemetry on your machine. See
[`docs/OBSERVABILITY.md`](../../docs/OBSERVABILITY.md) for the full guide.

## Quick start

```sh
docker compose -f deploy/observability/compose.yaml up -d
```

Then run any `mintmory` command, or start `mintmory-mcp`. MintMory exports when
no `MINTMORY_OTEL_ENABLED` is set and the collector answers on
`localhost:4318`.

- Traces: open <http://localhost:16686>, pick the service `mintmory-cli` or
  `mintmory-mcp` and search.
- Metrics: open <http://localhost:9090> and query

  ```promql
  histogram_quantile(0.95, sum by (le, phase) (rate(mintmory_search_latency_ms_bucket[5m])))
  ```

  This needs a long-running process such as the API or an MCP server: a one-shot
  CLI command exports once, under its own `service.instance.id`, so Prometheus
  has little to rate over.

## MintMory API in the stack

The optional `api` profile builds and runs the repository's `Dockerfile`,
wired to the collector, with its database in a named volume:

```sh
docker compose -f deploy/observability/compose.yaml --profile api up -d --build
```

## Configuration

Copy `.env.example` to `deploy/observability/.env` and edit it to change the
published ports, the bind address or the image tags. Every `MINTMORY_OBS_*`
variable and its default is documented there.

## Stopping

```sh
docker compose -f deploy/observability/compose.yaml down
docker compose -f deploy/observability/compose.yaml down -v
```

`down` stops and removes the containers; `down -v` also drops the
`mintmory-data` volume that holds the API database.
