# Design: telemetry runtime

## Decisions

- **Init failure turns telemetry off, never raises, and logs only the exception class**: telemetry never blocks
  MintMory, and messages can carry endpoint or header values. Checked on 1.42.1: the OTLP exporters raise `ValueError`
  for `OTEL_EXPORTER_OTLP_TIMEOUT=abc` or `OTEL_EXPORTER_OTLP_COMPRESSION=zip`.
- **Entry points without `Settings` call `init_telemetry(default_service_name=...)`, no settings, no guard.**
  `Settings` has no `env_file`, so `OTelSettings()` reads what `load_settings().otel` reads, but `load_settings()`
  also validates every other group (it raises on `MINTMORY_SUMMARY_CONCURRENCY=0`); telemetry must not turn that into
  a failure of every CLI command or server start. The API lifespan already loads `Settings` and passes `settings.otel`.
- **`none` for a signal builds no provider; injecting one signal turns the other off**: no exporter thread or network
  that nobody asked for, and tests never build a network exporter by accident.
- **`mark_error` lives here** because heavy-path (ordered before boundary) and boundary both need it.
- **`shutdown_telemetry` owns all teardown, the logger level included**: a level restored only by reset would be
  saved as CRITICAL by the next init.
- **Test fixtures live in the root `conftest.py`**: pytest runs with `--import-mode=importlib` and no test folder is on
  `sys.path`, while root fixtures reach `packages/*/tests` (checked with pytest 9.1.0 on this layout).
- **The SDK-missing WARNING also fires for explicit `true`**, a misconfiguration; `auto` with nothing set stays silent.
