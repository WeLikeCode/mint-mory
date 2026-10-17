# Questions — add-telemetry-boundary-tracing

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | accepted | 2.1 | technical | packages/api/tests/test_telemetry_http.py:397 expects two duration data points for records with identical attributes |
<!-- l4:index:end -->

---

## Q-001: packages/api/tests/test_telemetry_http.py:397 expects two duration data points for records with identical attributes

- **Status:** accepted
- **Blocking tasks:** 2.1
- **Kind:** technical
- **Asked:** 2026-10-17T20:38Z by deepseek, run r-20261017T1947Z-9dba, task 2.1

### Context
test_cancelled_request_and_no_response_at_all runs two ASGI-harness requests (both GET /x, no route, no response) and asserts len(points) == 2, with every point's attributes exactly {"http.request.method": "GET"}. OpenTelemetry SDK 1.42.1 aggregates histograms by attribute set with cumulative temporality (opentelemetry/sdk/metrics/_internal/_view_instrument_match.py keys aggregations by frozenset(attributes.items())), so two records with identical attributes produce ONE data point with count == 2. The same file's test_request_duration_recorded (line 613) asserts exactly that for two identical GET /stats requests (len(points) == 1, count == 2), and the spec's metric requirement lists only http.request.method, http.route and http.response.status_code (absent ones omitted), so no implementation can produce two same-attribute points in one metric stream. The spec scenario says 'the duration point has http.request.method=GET and no other attribute' (singular).

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/api/tests/test_telemetry_http.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit add-telemetry-boundary-tracing`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/api/tests/test_telemetry_http.py`: change line 397 from `assert len(points) == 2, points` to `assert len(points) == 1, points` (the existing loop then checks the single aggregated point; optionally add `assert points[0].count == 2`).

### Clarifier suggestion
Edit `packages/api/tests/test_telemetry_http.py`: change line 397 from `assert len(points) == 2, points` to `assert len(points) == 1, points` (the existing loop then checks the single aggregated point; optionally add `assert points[0].count == 2`).

### Answer
<!-- write below this line -->
