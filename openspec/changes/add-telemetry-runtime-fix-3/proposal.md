# Proposal: fix 3 for add-telemetry-runtime

## Why
Requested by CiprianSpot, 2026-10-17T01:24:11Z in FB-005 (refactor, packages/core/src/mintmory/core/telemetry.py:585-595, packages/core/src/mintmory/core/telemetry.py:613-635): span(), add_count() and record_value() check _enabled and _tracer or _meter, then read the module global again to use it, and _instrument() reads _meter once more. A shutdown_telemetry() on another thread between the check and the use sets the global to None, and the call raises AttributeError ('NoneType' object has no attribute 'start_as_current_span' or 'create_counter'), although telemetry must never break its caller. Read each global once into a local and use only the local: span() reads _tracer once; add_count() and record_value() read _meter once and pass it to _instrument(), which takes the meter as a parameter instead of reading _meter. No lock is needed: a tracer or meter taken before the shutdown stays usable, and its provider drops what it gets after the shutdown. Behaviour is otherwise unchanged and the existing tests stay as they are.

    def span(name: str, **attrs: Any) -> Iterator[Any]:
        """Context manager: a real span when enabled, else a cheap no-op."""
        if not _enabled or _tracer is None:
            yield _NoopSpan()
            return
        with _tracer.start_as_current_span(name) as sp:
            for key, value in attrs.items():
                if value is not None:
                    sp.set_attribute(key, value)
            yield sp
    def _instrument(kind: str, factory_name: str, name: str) -> Any:
        inst = _instruments.get(name)
        if inst is None and _meter is not None:
            inst = getattr(_meter, factory_name)(name)
            _instruments[name] = inst
        return inst


    def add_count(name: str, value: int = 1, **attrs: Any) -> None:
        if not _enabled or _meter is None:
            return
        counter = _instrument("counter", "create_counter", name)
        if counter is not None:
            counter.add(value, {k: v for k, v in attrs.items() if v is not None})


    def record_value(name: str, value: float, **attrs: Any) -> None:
        if not _enabled or _meter is None:
            return
        hist = _instrument("histogram", "create_histogram", name)
        if hist is not None:
            hist.record(value, {k: v for k, v in attrs.items() if v is not None})

Requested by CiprianSpot, 2026-10-17T01:24:12Z in FB-006 (behaviour, packages/core/src/mintmory/core/telemetry.py:541-551): init_telemetry() with span_exporter or metric_reader returns False silently when the OpenTelemetry SDK is missing. The caller asked for telemetry with its own exporter, so say why it is off, as the MINTMORY_OTEL_ENABLED=true branch already does: one WARNING on mintmory.telemetry that names the missing SDK and the extra to install.

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

The verifier found problems in `add-telemetry-runtime` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-64545f65 (major): Feedback FB-005 (refactor): span, add_count and record_value read _tracer and _meter once
- F-27a3cee6 (major): Feedback FB-006 (behaviour): an injected exporter without the SDK says why telemetry is off

## Impact
The code and the tests of `add-telemetry-runtime`.
