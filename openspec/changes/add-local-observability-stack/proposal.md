# Change: a local Jaeger stack, a doctor check and a guide for MintMory telemetry (OpenTelemetry, part 4 of 4)

## Why

Parts 1 to 3 make MintMory export traces and metrics to any OTLP collector, and switch on by themselves when one
answers on `localhost:4318`. A developer still needs a collector and a viewer, a way to check what MintMory sees,
and a guide. `docs/OBSERVABILITY.md` section 4.5 only suggests "`jaegertracing/all-in-one` on `:4318`" in prose.
With `otel.enabled: false` (its default) the chart renders no `MINTMORY_OTEL_ENABLED` key, so under the new `auto`
default it would no longer switch telemetry off; it also cannot set sampling.

## What changes

- `deploy/observability/`: a Docker Compose stack with an OpenTelemetry Collector (OTLP in on `4317`/`4318`),
  Jaeger 2 (trace UI on `16686`) and Prometheus (metrics UI on `9090`). The collector sends traces to Jaeger and
  serves metrics to Prometheus. Ports, bind address and image tags are variables with defaults, documented in an
  `.env.example`. An optional profile `api` builds and runs the MintMory API from the repository's `Dockerfile`,
  wired to the collector. All images are pinned to exact versions.
- `mintmory doctor` prints a telemetry row: mode, state, endpoint, whether the endpoint answers, service name.
- Helm: `otel.enabled: false` renders `MINTMORY_OTEL_ENABLED: "false"`; `otel.sampler`, `otel.samplerArg` and
  `otel.resourceAttributes` set the standard variables.
- `docs/OBSERVABILITY.md` section 4 becomes the user guide: modes, variables and their precedence, the local stack in
  three commands, how to find a bottleneck in Jaeger and Prometheus, and production settings.

## Non-goals

Grafana dashboards, alerting, log collection, and any change to application telemetry (parts 1 to 3).

## Impact

- New: `deploy/observability/compose.yaml`, `otel-collector.yaml`, `prometheus.yml`, `.env.example`, `README.md`.
- Changed: `packages/cli/src/mintmory/cli/main.py` (`doctor`), `packages/core/src/mintmory/core/telemetry.py` (a
  status function), `deploy/helm/mintmory/templates/configmap.yaml`, `values.yaml`, `values.schema.json`,
  `docs/OBSERVABILITY.md`, `README.md` (one pointer).
- Depends on `add-telemetry-runtime` (the variables and modes it documents and reports), and on
  `add-telemetry-heavy-path-spans` and `add-telemetry-boundary-tracing`, whose spans and metrics
  (`mintmory.search.*`, `mintmory_search_latency_ms`, `gen_ai.chat`, `traceparent`) the guide documents and which also
  edit `docs/OBSERVABILITY.md` section 4. It edits Helm files that
  `deployment-hardening` does not (`configmap.yaml`, `values.yaml`, `values.schema.json`); rebase if that change merges
  first.
