# Proposal: fix 2 for add-telemetry-heavy-path-spans

## Why
The verifier found problems in `add-telemetry-heavy-path-spans` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- H-e0757174 (major): Rejected hold: the diff is longer than 120000 characters: the judge saw only the start: Decided by human in Q-003: an independent full-diff review (51/51 unit tests and the full gate pass; with telemetry off every command matches the base) found two breaks of this spec's rule that recording a metric point or attribute SHALL never raise into the caller (spec.md line 35; tasks.md asks for try/except). (1) telemetry.counts_added (telemetry.py:1006) calls add_count outside its try, and add_count does not guard counter.add or the instrument creation: with a failing meter, storage add_memory (storage.py:468, storage_postgres.py:418) raises RuntimeError after the row is stored, so mintmory add exits non-zero and a retry stores a duplicate. (2) span() sets attributes without a guard (telemetry.py:630), so embed_span and file_span make embed() raise when set_attribute raises. WHEN the meter, a counter's add, a histogram's record or a span's set_attribute raises inside a telemetry helper (counts_added, add_count, record_value, the span attributes of embed_span and file_span) THEN the error stays inside telem. Change the behaviour the hold names as the human's reason says; the reason en...

## Impact
The code and the tests of `add-telemetry-heavy-path-spans`.
