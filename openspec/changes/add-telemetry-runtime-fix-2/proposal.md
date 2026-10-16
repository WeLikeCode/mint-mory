# Proposal: fix 2 for add-telemetry-runtime

## Why
Requested by CiprianSpot, 2026-10-16T21:28:28Z in FB-003 (behaviour, packages/core/src/mintmory/core/telemetry.py:541-568): The check of _enabled runs outside the lock and is not repeated inside it, so two threads that call init_telemetry at the same time both build providers: the second is installed as the module provider while the first stays the global one, spans reach only the first exporter, and shutdown_telemetry flushes the orphan, never the global provider. The spec says init and shutdown share one lock and a later init changes nothing. Repeat the _enabled check inside the lock (double-checked) so exactly one init builds.

        if _enabled:
            return True

        injected = span_exporter is not None or metric_reader is not None
        if injected:
            if not _sdk_available():
                return False
            traces_exporter = "injected" if span_exporter is not None else "none"
            metrics_exporter = "injected" if metric_reader is not None else "none"
        else:
            traces_exporter = _resolve_exporter(settings, "TRACES")
            metrics_exporter = _resolve_exporter(settings, "METRICS")
            if traces_exporter == "none" and metrics_exporter == "none":
                return False
            state = _resolve_state(settings)
            if state == "off" or state == "no collector":
                return False
            if state == "sdk missing":
                if settings.enabled == "true" or _has_endpoint_variable():
                    _LOGGER.warning(
                        "OpenTelemetry export requested but the SDK is missing; "
                        "install 'mintmory-core[otel]'"
                    )
                return False

        with _shutdown_lock:
            try:
                return _activate(

Requested by CiprianSpot, 2026-10-16T21:28:28Z in FB-004 (behaviour, packages/core/src/mintmory/core/config.py:220-231): On staging, the setting was a pydantic bool, so 1, yes and on (any case) meant true and 0, no and off meant false. Now 1, yes and on become auto with a WARNING, which silently changes what a deployed setting does. Keep every spelling pydantic's boolean parser accepts, mapped to true or false, and keep auto as the third value.

        @field_validator("enabled", mode="before")
        @classmethod
        def _normalise_enabled(cls, value: object) -> object:
            if isinstance(value, bool):
                return "true" if value else "false"
            if value is None:
                return value
            normalised = str(value).strip().lower()
            if normalised in ("auto", "true", "false"):
                return normalised
            _OTEL_LOGGER.warning("MINTMORY_OTEL_ENABLED=%r is invalid; falling back to 'auto'", value)
            return "auto"

The verifier found problems in `add-telemetry-runtime` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-88eb7d41 (major): Feedback FB-003 (behaviour): init_telemetry: one set of providers when two threads init at once
- F-9b72c55d (major): Feedback FB-004 (behaviour): MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before

## Impact
The code and the tests of `add-telemetry-runtime`.
