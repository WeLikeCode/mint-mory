# Change: API health endpoints + OpenTelemetry export wiring (MM-42)

## Why

Making MintMory deployable on Kubernetes needs three small enabling changes in the
REST API / telemetry layer (a Fable deployability audit found the app otherwise
architecturally ready):

1. **No health/readiness endpoints.** `api/app.py` exposes no `/healthz`,
   `/readyz`, or liveness route (only heavy `GET /stats`). K8s needs cheap
   liveness + readiness probes.
2. **OpenTelemetry never activates.** `core/telemetry.py:init_telemetry()` is a
   correct, idempotent activator — but **no entrypoint ever calls it**
   (grep across api/mcp/cli finds only the definition). So even with
   `MINTMORY_OTEL_ENABLED=true` the app runs the no-op shim and emits nothing.
3. **Metrics can't reach a collector.** When `exporter="otlp"`, spans use
   `OTLPSpanExporter`, but the metric reader is hard-coded to
   `ConsoleMetricExporter` (`telemetry.py:99`). The existing metrics
   (`mintmory.llm.latency_ms`, `mintmory.llm.calls`, dream durations) never leave
   the pod.

These are the code prerequisites for the Helm chart (MM-43), which wires probes to
the endpoints and an OTLP collector endpoint to the exporter.

## What changes

- **Health endpoints in `api/app.py`:**
  - `GET /healthz` — liveness: returns 200 `{"status":"ok"}` when the process is
    up (does not touch the DB, so a slow store never kills the pod).
  - `GET /readyz` — readiness: runs a cheap `SELECT 1` through the store; 200
    `{"status":"ready"}` on success, 503 otherwise. Both are unauthenticated,
    untagged (or a `Health` tag), and excluded from any future auth by living
    outside the domain routes (probes hit the pod directly, bypassing ingress).
- **Activate telemetry at API startup:** call `init_telemetry(load_settings().otel)`
  in the FastAPI `lifespan` (before `yield`). No-op and zero-cost when
  `MINTMORY_OTEL_ENABLED` is false or the `[otel]` extra is absent (unchanged
  default behaviour — the shim already guards this).
- **OTLP metric export in `telemetry.py`:** when `settings.exporter == "otlp"`, use
  `OTLPMetricExporter` for the `PeriodicExportingMetricReader` (mirroring the
  existing span-exporter branch); keep `ConsoleMetricExporter` for
  `exporter="console"`. So both traces AND metrics reach the OTLP endpoint
  (`OTEL_EXPORTER_OTLP_ENDPOINT`).

Non-goals here: the Dockerfiles and Helm chart (MM-43); auth (ingress-nginx handles
it); changing default behaviour (OTel stays off by default; endpoints are additive).
The prod start command (`uvicorn ... --workers 1`, no `--reload`) is a chart/CMD
concern, documented in MM-43, not a code change.

## Impact

- Affected specs: **deployment** (new capability: health probes + telemetry export).
- Affected code: `packages/api/src/mintmory/api/app.py` (two routes + a one-line
  lifespan call), `packages/core/src/mintmory/core/telemetry.py` (OTLP metric
  exporter branch). Tests for both.
- Migrations: none. Defaults unchanged (OTel off; `/healthz`/`/readyz` are additive
  and unauthenticated by design).
