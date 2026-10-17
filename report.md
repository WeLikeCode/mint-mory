# Delivery plan telemetry-and-fixes

- Status: stopped
- Repository: https://github.com/WeLikeCode/mint-mory
- Target: staging at c902d8e86dc79dcd0bd6c54c238ac81a4de21ae2
- Merge: auto
- No promotion target is set. Promotion was not performed.
- Written: 2026-10-17T03:54:06Z
- Stopped: unit_halted (openspec:fix-distiller-prompt-cap): secret in the outgoing commits, push blocked: packages/core/tests/test_history_distill_phase2.py (mintkey)

## Units

### openspec:fix-markdown-cleanup-fences
- Result: integrated at e0d968f6c26f5ff7ffc1d236c4a61137e60bf0dd
- Pull request: 4
- Merge commit: e0d968f6c26f5ff7ffc1d236c4a61137e60bf0dd
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $0.65, 1 run(s), 1 attempt(s)

### openspec:add-telemetry-runtime
- Result: integrated at ff7e3dae5e2579ecc3c704a7d73f66e6d873d24f
- Pull request: 6
- Merge commit: ff7e3dae5e2579ecc3c704a7d73f66e6d873d24f
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $6.70, 16 run(s), 1 attempt(s)
- Accepted review findings (accepted by ciprian@spotus.space (agent): Resolve both findings while writing the tests. F-1619b9: a shared standard variable is validated once, where it is read: one WARNING per bad variable on mintmory.telemetry, never one per signal; OTEL_EXPORTER_OTLP_PROTOCOL is checked once when any signal uses OTLP, so 'Bad standard values fall back' expects exactly two WARNINGs (OTEL_TRACES_EXPORTER and OTEL_EXPORTER_OTLP_PROTOCOL). F-0ad188: _Scrubbing keeps the exporter it wraps in _inner, as _GuardedSpanExporter does; the exporter-type test follows _inner until an object has none and asserts the innermost exporter's type (the OTLP HTTP span exporter).):
  - F-1619b9 [testability/major] Scenario 'Bad standard values fall back' needs exactly two WARNINGs on `mintmory.telemetry`: `OTEL_TRACES_EXPORTER` and `OTEL_EXPORTER_OTLP_PROTOCOL`. In that scenario traces use console. Metrics use the default `otlp` exporter, because `MINTMORY_OTEL_EXPORTER` is unset. The spec does not say whether the protocol is checked for each signal or only for a signal that uses OTLP. It also does not say whether one invalid shared variable warns once or once per signal. Checking per signal gives three WARNINGs and the assertion fails. The implementer has to guess the rule.: addressed by the verifier
  - F-0ad188 [interfaces/major] Task 7.1 says the exporter-type test checks `captured[-1]._inner`. Task 4b.2 makes `_Scrubbing` the outermost wrapper on every span exporter, and task 4.3 puts the OTLP exporter behind `_GuardedSpanExporter._inner`. So the exporter handed to the processor is `_Scrubbing`, and one `_inner` hop reaches the guard, not the OTLP exporter. The spec does not say whether `_Scrubbing` keeps an `_inner` attribute. It also does not say which object `captured` holds or how many hops the test follows. The edit to the existing test therefore cannot be implemented as written.: addressed by the verifier
  - F-fea82d [interfaces/minor] `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER` can be comma lists. The spec defines only the fallback for an unknown list, 'first known item'. It does not say what a fully valid multi-item list such as `console,otlp` does: use the first item only, or build several exporters. The signatures of `_service_name`, `_resolve_state` and `_traces_endpoint` appear only in tasks, and part 4 reuses them.: addressed by the verifier
  - F-5d64eb [failure_cases/minor] Several cases are not stated. (1) Another component has already set a global tracer or meter provider, so `set_tracer_provider` is a no-op while the spec promises library spans reach the same exporters. (2) Injected exporters with the SDK missing: is there a WARNING? (3) `MINTMORY_OTEL_ENABLED=true` together with `OTEL_SDK_DISABLED=true` and the SDK missing: does it warn? (4) A guard's `shutdown` or `force_flush` raising inside the shutdown daemon thread. (5) `span()` or `add_count` running while `shutdown_telemetry` clears `_tracer` and `_meter`.: addressed by the verifier
  - F-f4dc92 [testability/minor] Scenario 'Exit is bounded when export hangs' leaves a live thread blocked on an Event that is never set. It does not say the test must set the Event at the end, so the thread leaks past the test and the autouse reset. Scenario 'Auto with no collector stays off' runs in a subprocess. It does not say the subprocess must unset `MINTMORY_OTEL_ENABLED`, which the root conftest defaults to `false` and a child process inherits. It also does not say how `_endpoint_reachable` is patched in the child. `otlp_receiver.spans()` returns tuples, but the scenarios say it 'contains `x`' without saying whether that means the name or the tuple.: addressed by the verifier

### openspec:add-telemetry-entry-points
- Result: integrated at 40691bd6a09afdead8a38a37711e6b812744951c
- Pull request: 14
- Merge commit: 40691bd6a09afdead8a38a37711e6b812744951c
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $0.72, 2 run(s), 1 attempt(s)

### openspec:add-telemetry-heavy-path-spans
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)
- Accepted review findings (accepted by ciprian@spotus.space (agent): Resolve both findings. F-8f538f: type the kind parameter of telemetry.span() as str (an unknown value maps to INTERNAL, as the spec says), so the 'Options reach the span' test with kind='bogus' passes mypy strict without type: ignore or cast. F-b98cfc: add one test per helper failure: an embedder whose embed_batch raises gives one mintmory.embed span with status ERROR (mark_error) and one latency point, and re-raises; a ConversionError in mintmory.convert and a VisionError in mintmory.vision.caption give mintmory.outcome=failed and ERROR; a caught CoChangeUnavailable gives mintmory.outcome=unavailable and no ERROR; the index-tree scenario also asserts mintmory.files.updated, .unchanged and .failed (0, 0, 0 on the first run; after one file is modified and index-tree runs again, updated=1 and unchanged=1).):
  - F-8f538f [contradiction/major] Task 1.2 types `kind` as `Literal["internal","server","client"]`. The scenario "Options reach the span" calls `telemetry.span("d", kind="bogus")`. The tasks note that `mypy packages` (a gate in 6.1) also checks tests in strict mode. The Literal signature and the bogus-value test cannot both pass the mypy gate as written. The spec gives the implementer no way to resolve this: it could widen the type to `str`, or add a `type: ignore` or `cast` in the test.: no answer recorded
  - F-b98cfc [testability/major] The requirement "Span helpers without work or with a failure" says every helper (`search_phase`, the embed decorator, `mintmory.convert`, `mintmory.vision.caption`, `command_span`) marks the span with `mark_error`, records its metric point, and re-raises. Only `search_phase` (the fts failure) and `command_span` have scenarios. Nothing tests a failing embedder, a `ConversionError` or `VisionError` giving `mintmory.outcome=failed` plus ERROR, or `mintmory.outcome=unavailable` when `CoChangeUnavailable` is caught (no ERROR). Nothing tests `mintmory.files.updated`, `.unchanged` or `.failed`; the scenario checks only `scanned` and `added`. These are stated SHALLs without a decidable test.: no answer recorded
  - F-f16ad5 [interfaces/minor] Several names are left to the implementer: the embed decorator has no name or signature, only "one shared decorator" and a `__wrapped__` check. `command_span(name)` does not say whether the argument is `history sync` or `history.sync`; the spec only says spaces become dots. Task 4.2 does not say where `index-tree` calls `set_attributes`, so the current span must be the command span, not the scan span. For `SystemExit`, the rule for "non-zero" is not fixed (`.code` can be None or a string). `timed_phase` (`span=False`) has no span to mark on failure, and the spec does not say what it does.: no answer recorded
  - F-be00f0 [testability/minor] The Postgres scenario says only that `PostgresBackend` is built without a database and that "data-access methods are patched". It does not name the methods `search` calls or what they return. The implementer must discover this from the repository. It is also not stated that the constructor works without a driver or database.: no answer recorded
  - F-1aba09 [testability/minor] The "Conversion spans" scenario runs `mintmory ingest report.pdf` with only `extract_markdown` patched. It does not say the file exists. The "failing command" scenario says a nonexistent path makes ingest exit 1, so a test that does not create the file would produce an ERROR span instead of the expected child span.: no answer recorded
  - F-3ff0a7 [testability/minor] In the privacy scenario, the dream summary only reaches the test LLM server if the three memories meet the default `SummarySettings.min_memories`, which is not shown. `build_dreaming_engine(store, LLMSettings(...))` is used with a second argument whose signature is not shown. The claim that the `Authorization` header carries the key under `provider="ollama"` is not verified. The test asserts only that the server saw a chat request, so the key check may be vacuous.: no answer recorded
  - F-26da38 [outcome/minor] "Telemetry carries no content" lists the existing spans as compliant (`gen_ai.chat`, the dream spans, the LLM and dream metrics). It does not list the attributes of the `traced` spans `mintmory.search` and `mintmory.add_memory`. Those spans are exercised by the sentinel tests and by the new `mintmory.cli.add` parent.: no answer recorded
  - F-89e0b1 [feasibility/minor] The unit touches `telemetry.py`, both storage backends, `hybrid_search.py`, `embedder.py`, history ingest, `dreaming.py` and `cli/main.py`, and adds about 20 scenarios. It is large for one automatic run but cohesive. The spec relies on unseen `staging` code: `_instrument` accepting `unit`, `anchor_candidates` not calling `fuse_and_search`, and the history commands living in `cli/main.py`. If anchoring did call `fuse_and_search`, the "anchoring records no phase" test would fail, because task 2.2 puts `search_phase("fusion")` there.: no answer recorded

### openspec:add-telemetry-boundary-tracing
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:add-local-observability-stack
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:fix-note-bonus-env-name
- Result: integrated at 61ee36d119da2c4e99cf1352c976ec068b4ed7ef
- Pull request: 16
- Merge commit: 61ee36d119da2c4e99cf1352c976ec068b4ed7ef
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $0.57, 1 run(s), 1 attempt(s)

### openspec:fix-distiller-prompt-cap
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.11, 1 run(s), 1 attempt(s)

### openspec:fix-cochange-tools-on-postgres
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:add-recurrent-tree-indexing
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:deployment-hardening
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

## Batches

- warm-up (profile none): accepted at 7942c5591c0bcd29f2f50fabefeea04ea99fe9f9
- telemetry (profile none): not checked
- fixes (profile none): not checked

## Usage

- Cost: $19.46
- Of which the readiness review: $10.70
- Runs that dispatched a unit: 21
