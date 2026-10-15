# Tasks: API health endpoints + OTel export wiring (MM-42)

## 1. Health endpoints (`api/app.py`)
- [x] `GET /healthz` — liveness, no DB touch, 200 `{"status":"ok"}`.
- [x] `GET /readyz` — readiness, cheap `SELECT 1` via `get_store().connect()`;
  200 `{"status":"ready"}` or 503 on failure. Both unauthenticated (probes hit the
  pod directly).

## 2. Telemetry activation (`api/app.py` lifespan)
- [x] In `lifespan`, after store init, call `init_telemetry(load_settings().otel)`.
  No-op when disabled / SDK absent (unchanged default).

## 3. OTLP metric exporter (`core/telemetry.py`)
- [x] Choose the metric exporter by `settings.exporter`: `OTLPMetricExporter` for
  `"otlp"`, else `ConsoleMetricExporter`. Mirror the existing span branch.
- [x] Confirm the `[otel]` extra provides the OTLP HTTP metric exporter (same
  `opentelemetry-exporter-otlp-proto-http` distribution); add the pin if missing.

## 4. Tests
- [x] `/healthz` 200 (no store needed); `/readyz` 200 with store, 503 when
  `SELECT 1` fails.
- [x] Default (OTel off): `init_telemetry` returns False, instrumentation stays
  no-op. Enabled + otlp (SDK present / importorskip): returns True and uses the
  OTLP metric exporter branch (assert construction, not delivery — non-flaky).

## 5. Gates
- [x] `ruff` + `ruff format` clean; `mypy packages` clean.
- [x] `pytest -q` ≥ 80%; full suite green.
- [x] `openspec validate add-api-health-and-otel --strict`.
