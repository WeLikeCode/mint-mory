# Proposal: fix 1 for add-telemetry-runtime

## Why
Requested by CiprianSpot, 2026-10-16T16:54:38Z in FB-001 (behaviour): _sdk_available must catch ImportError and ValueError from importlib.util.find_spec and return False; add a test that does not stub _sdk_available (monkeypatch importlib.util.find_spec to raise ModuleNotFoundError)

Requested by CiprianSpot, 2026-10-16T16:54:38Z in FB-002 (behaviour): _build_meter_provider must wrap the configured metric exporter with _GuardedMetricExporter as the span exporter is wrapped, keeping the reader's temporality; packages/api/tests/test_health_and_otel.py must unwrap _inner to the OTLP metric exporter (task 7.1)

The verifier found problems in `add-telemetry-runtime` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-e875fe5d (major): Feedback FB-001 (behaviour): _sdk_available must catch ImportError and ValueError from
- F-a9f95a8b (major): Feedback FB-002 (behaviour): _build_meter_provider must wrap the configured metric exporter with

## Impact
The code and the tests of `add-telemetry-runtime`.
