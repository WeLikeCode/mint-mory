# Feedback — add-telemetry-runtime

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | addressed | behaviour |  | _sdk_available must catch ImportError and ValueError from |
| FB-002 | addressed | behaviour |  | _build_meter_provider must wrap the configured metric exporter with |
| FB-003 | addressed | behaviour | packages/core/src/mintmory/core/telemetry.py:541 | init_telemetry: one set of providers when two threads init at once |
| FB-004 | addressed | behaviour | packages/core/src/mintmory/core/config.py:220 | MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before |
| FB-005 | submitted | refactor | packages/core/src/mintmory/core/telemetry.py:585 | span, add_count and record_value read _tracer and _meter once |
| FB-006 | submitted | behaviour | packages/core/src/mintmory/core/telemetry.py:541 | an injected exporter without the SDK says why telemetry is off |
<!-- l4:feedback-index:end -->

---

## FB-001: _sdk_available must catch ImportError and ValueError from

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-16T16:54:38Z

### Feedback
_sdk_available must catch ImportError and ValueError from importlib.util.find_spec and return False; add a test that does not stub _sdk_available (monkeypatch importlib.util.find_spec to raise ModuleNotFoundError)

### When / Then
- **When:** init_telemetry() runs and the opentelemetry package is not installed (importlib.util.find_spec raises ModuleNotFoundError for opentelemetry.sdk)
- **Then:** it returns False without raising; in auto mode it logs nothing, in true mode it logs one WARNING that names mintmory-core[otel]

### Outcome
<!-- written by the harness -->
Addressed in round 7 at dc31486655: telemetry.py _sdk_available catches (ImportError, ValueError); test_telemetry_sdk_probe tests pass

---

## FB-002: _build_meter_provider must wrap the configured metric exporter with

- **Status:** addressed
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-16T16:54:38Z

### Feedback
_build_meter_provider must wrap the configured metric exporter with _GuardedMetricExporter as the span exporter is wrapped, keeping the reader's temporality; packages/api/tests/test_health_and_otel.py must unwrap _inner to the OTLP metric exporter (task 7.1)

### When / Then
- **When:** a metric export fails because the configured OTLP collector is unreachable (endpoint on a closed port, three force_flush calls)
- **Then:** exactly one WARNING 'telemetry: metric export failed' is logged per failure streak on the mintmory.telemetry logger

### Outcome
<!-- written by the harness -->
Addressed in round 7 at dc31486655: telemetry.py _build_meter_provider wraps via _guarded_metric_exporter_class()(exporter); api test unwraps _inner

---

## FB-003: init_telemetry: one set of providers when two threads init at once

- **Status:** addressed
- **Kind:** behaviour
- **Where:** `packages/core/src/mintmory/core/telemetry.py:541-568`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-16T21:28:28Z

### Code
```python
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
```

### Feedback
The check of _enabled runs outside the lock and is not repeated inside it, so two threads that call init_telemetry at the same time both build providers: the second is installed as the module provider while the first stays the global one, spans reach only the first exporter, and shutdown_telemetry flushes the orphan, never the global provider. The spec says init and shutdown share one lock and a later init changes nothing. Repeat the _enabled check inside the lock (double-checked) so exactly one init builds.

### When / Then
- **When:** two threads call init_telemetry at the same time (for example behind a threading.Barrier, each with its own span_exporter)
- **Then:** exactly one set of providers is built and installed as the global ones, the other call returns the same result without building, and shutdown_telemetry flushes and shuts down that one set

### Outcome
<!-- written by the harness -->
Addressed in round 7 at dc31486655: telemetry.py init_telemetry: `with _shutdown_lock: if _enabled: return True`

---

## FB-004: MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before

- **Status:** addressed
- **Kind:** behaviour
- **Where:** `packages/core/src/mintmory/core/config.py:220-231`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-16T21:28:28Z

### Code
```python
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
```

### Feedback
On staging, the setting was a pydantic bool, so 1, yes and on (any case) meant true and 0, no and off meant false. Now 1, yes and on become auto with a WARNING, which silently changes what a deployed setting does. Keep every spelling pydantic's boolean parser accepts, mapped to true or false, and keep auto as the third value.

### When / Then
- **When:** MINTMORY_OTEL_ENABLED is 1, yes, on, 0, no or off (any case)
- **Then:** the mode is true for 1, yes and on and false for 0, no and off, with no WARNING; auto, true and false (any case) keep their meaning; any other value still falls back to auto with a WARNING

### Outcome
<!-- written by the harness -->
Addressed in round 7 at dc31486655: config.py _TRUE_SPELLINGS/_FALSE_SPELLINGS in _normalise_enabled

---

## FB-005: span, add_count and record_value read _tracer and _meter once

- **Status:** submitted
- **Kind:** refactor
- **Where:** `packages/core/src/mintmory/core/telemetry.py:585-595`
- **Where:** `packages/core/src/mintmory/core/telemetry.py:613-635`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-17T01:24:11Z

### Code
`packages/core/src/mintmory/core/telemetry.py:585-595`
```python
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
```
`packages/core/src/mintmory/core/telemetry.py:613-635`
```python
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
```

### Feedback
span(), add_count() and record_value() check _enabled and _tracer or _meter, then read the module global again to use it, and _instrument() reads _meter once more. A shutdown_telemetry() on another thread between the check and the use sets the global to None, and the call raises AttributeError ('NoneType' object has no attribute 'start_as_current_span' or 'create_counter'), although telemetry must never break its caller. Read each global once into a local and use only the local: span() reads _tracer once; add_count() and record_value() read _meter once and pass it to _instrument(), which takes the meter as a parameter instead of reading _meter. No lock is needed: a tracer or meter taken before the shutdown stays usable, and its provider drops what it gets after the shutdown. Behaviour is otherwise unchanged and the existing tests stay as they are.

### Outcome
<!-- written by the harness -->

---

## FB-006: an injected exporter without the SDK says why telemetry is off

- **Status:** submitted
- **Kind:** behaviour
- **Where:** `packages/core/src/mintmory/core/telemetry.py:541-551`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-17T01:24:12Z

### Code
```python
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
```

### Feedback
init_telemetry() with span_exporter or metric_reader returns False silently when the OpenTelemetry SDK is missing. The caller asked for telemetry with its own exporter, so say why it is off, as the MINTMORY_OTEL_ENABLED=true branch already does: one WARNING on mintmory.telemetry that names the missing SDK and the extra to install.

### When / Then
- **When:** init_telemetry() is called with a span_exporter or a metric_reader and the OpenTelemetry SDK is not installed (_sdk_available() returns False)
- **Then:** it returns False, installs no provider, and logs exactly one WARNING on the mintmory.telemetry logger that names the missing SDK and mintmory-core[otel]

### Outcome
<!-- written by the harness -->
