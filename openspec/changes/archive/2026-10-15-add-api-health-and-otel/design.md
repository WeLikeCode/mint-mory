# Design: API health endpoints + OTel export wiring (MM-42)

Small, additive, backward-compatible. Enables MM-43 (Helm chart).

## 1. Health endpoints (`api/app.py`)

```python
@app.get("/healthz", tags=["Health"])
async def healthz() -> dict[str, str]:
    """Liveness — process is up. Does NOT touch the DB (a slow store must not
    trigger pod restarts)."""
    return {"status": "ok"}

@app.get("/readyz", tags=["Health"])
async def readyz() -> dict[str, str]:
    """Readiness — the store is openable. Cheap `SELECT 1`; 503 if it fails."""
    try:
        get_store().connect().execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001 — readiness must degrade, not crash
        raise HTTPException(status_code=503, detail="store not ready") from exc
    return {"status": "ready"}
```

- Liveness deliberately DB-free: it answers "is the ASGI app serving?"; readiness
  answers "can it serve queries?". This is the standard split (a stuck DB should
  drop the pod out of the Service via readiness, not thrash-restart it via
  liveness).
- Uses the existing `get_store()`/`StorageAdapter.connect()` (single cached
  connection); `SELECT 1` is O(1).
- Unauthenticated by design: K8s probes hit the pod IP directly (bypassing
  ingress), and MM-43 puts basic-auth only on the ingress. No secret exposed.

## 2. Telemetry activation in lifespan (`api/app.py`)

In `lifespan`, before `yield`, after the store is initialised:
```python
from mintmory.core.telemetry import init_telemetry
init_telemetry(load_settings().otel)
```
`init_telemetry` is idempotent and returns False (no-op) when
`settings.otel.enabled` is false or the `[otel]` SDK is missing — so the default
offline behaviour is byte-identical. Only when `MINTMORY_OTEL_ENABLED=true` does it
wire the providers. (`load_settings()` is already imported in app.py.)

## 3. OTLP metric exporter (`core/telemetry.py`)

Replace the hard-coded console metric reader (telemetry.py:99) with an
exporter chosen by `settings.exporter`, mirroring the existing span branch:
```python
if settings.exporter == "otlp":
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    metric_exporter: Any = OTLPMetricExporter()
else:
    metric_exporter = ConsoleMetricExporter()
reader = PeriodicExportingMetricReader(metric_exporter)
```
Both span and metric exporters then honour `OTEL_EXPORTER_OTLP_ENDPOINT` (standard
OTLP env, read by the exporters). No new config field needed — `exporter` already
gates it. The `[otel]` extra must include the OTLP metric exporter package (it
already ships with `opentelemetry-exporter-otlp-proto-http`, which provides both
trace and metric HTTP exporters — verify the extra pins it; if only the trace
exporter is pinned, add the metric one — but they are the same distribution).

## 4. Edge cases

- `[otel]` not installed but `MINTMORY_OTEL_ENABLED=true` → `init_telemetry` logs a
  one-line warning and returns False (existing behaviour); app runs fine.
- `readyz` before lifespan completes → `get_store()` raises → 503 (correct: not
  ready).
- `exporter="otlp"` with no `OTEL_EXPORTER_OTLP_ENDPOINT` → the OTLP exporter uses
  its default `localhost:4318`; that's the exporter's contract, not ours.
- Calling `init_telemetry` twice (e.g. uvicorn reload) → idempotent (`if _enabled:
  return True`).

## 5. Testing

- `test_health.py` (FastAPI `TestClient`): `GET /healthz` → 200 `{"status":"ok"}`
  without needing a real store; `GET /readyz` → 200 with an initialised store, and
  503 when the store fails a `SELECT 1` (monkeypatch `get_store`/connect to raise).
- Telemetry: with `MINTMORY_OTEL_ENABLED=false` (default), `init_telemetry` returns
  False and instrumentation stays no-op (assert `is_enabled()` False after
  lifespan). With enabled + `exporter="otlp"` and the SDK present, assert
  `init_telemetry` returns True and the metric reader is built with the OTLP
  exporter (can assert the branch by monkeypatching the OTLP exporter import or by
  asserting no `ConsoleMetricExporter` is used when otlp). Keep it non-flaky (no
  real network export in tests — the PeriodicExportingMetricReader won't push in a
  short test window; assert construction, not delivery).
- Existing API tests stay green.

## 6. Gates

`ruff` + `ruff format` clean; `mypy packages` clean (CI command); `pytest -q` ≥ 80%
full suite green (`--extra cochange` env; otel extra available for the enabled-path
test or `importorskip`); `openspec validate add-api-health-and-otel --strict`.
