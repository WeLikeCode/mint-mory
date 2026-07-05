# Tasks: API health endpoints + OTel export wiring (MM-42)

## 1. Health endpoints (`api/app.py`)
- [ ] `GET /healthz` — liveness, no DB touch, 200 `{"status":"ok"}`.
- [ ] `GET /readyz` — readiness, cheap `SELECT 1` via `get_store().connect()`;
  200 `{"status":"ready"}` or 503 on failure. Both unauthenticated (probes hit the
  pod directly).

## 2. Telemetry activation (`api/app.py` lifespan)
- [ ] In `lifespan`, after store init, call `init_telemetry(load_settings().otel)`.
  No-op when disabled / SDK absent (unchanged default).

## 3. OTLP metric exporter (`core/telemetry.py`)
- [ ] Choose the metric exporter by `settings.exporter`: `OTLPMetricExporter` for
  `"otlp"`, else `ConsoleMetricExporter`. Mirror the existing span branch.
- [ ] Confirm the `[otel]` extra provides the OTLP HTTP metric exporter (same
  `opentelemetry-exporter-otlp-proto-http` distribution); add the pin if missing.

## 4. Tests
- [ ] `/healthz` 200 (no store needed); `/readyz` 200 with store, 503 when
  `SELECT 1` fails.
- [ ] Default (OTel off): `init_telemetry` returns False, instrumentation stays
  no-op. Enabled + otlp (SDK present / importorskip): returns True and uses the
  OTLP metric exporter branch (assert construction, not delivery — non-flaky).

## 5. Gates
- [ ] `ruff` + `ruff format` clean; `mypy packages` clean.
- [ ] `pytest -q` ≥ 80%; full suite green.
- [ ] `openspec validate add-api-health-and-otel --strict`.
