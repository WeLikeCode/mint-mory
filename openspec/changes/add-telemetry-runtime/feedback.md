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
| FB-001 | submitted | behaviour |  | _sdk_available must catch ImportError and ValueError from |
| FB-002 | submitted | behaviour |  | _build_meter_provider must wrap the configured metric exporter with |
<!-- l4:feedback-index:end -->

---

## FB-001: _sdk_available must catch ImportError and ValueError from

- **Status:** submitted
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

---

## FB-002: _build_meter_provider must wrap the configured metric exporter with

- **Status:** submitted
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
