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
| Q-002 | answered | 3.1 | harness | Task 3.1: the pre-satisfied check could not decide |
| Q-003 | answered | 3.1 | harness | Task 3.1: the pre-satisfied check could not decide |
| Q-004 | answered | 3.1 | harness | Task 3.1: the pre-satisfied check could not decide |
| Q-005 | answered | 3.2 | harness | Task 3.2: the pre-satisfied check could not decide |
| Q-006 | open | 4.1 | technical | packages/core/tests/test_telemetry_embedder_network.py:153 — frozen OpenAI stub rejects the extra_headers the spec requires |
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

---

## Q-002: Task 3.1: the pre-satisfied check could not decide

- **Status:** answered
- **Blocking tasks:** 3.1
- **Kind:** harness
- **Asked:** 2026-10-18T15:59Z by deepseek, run r-20261018T1548Z-8982, task 3.1
- **Criteria:** C-7d4fc8c6 (observability › MCP tool calls are traced once › The verified FastMCP version is installed)

### Context
L4 could not run the pre-satisfied check of task 3.1, so it does not count the failure against the agent: no attempt was used and no profile was escalated.
Why: its tests import no project module: the zero-value check cannot judge them
Runs: test-presatisfied, test-presatisfied, test-base-run
Kept real: packages/api/src/mintmory/api/app.py::main, packages/core/src/mintmory/core/telemetry.py::traced, packages/core/src/mintmory/core/telemetry.py::timed_phase, packages/core/src/mintmory/core/telemetry.py::counts_added, packages/core/src/mintmory/core/telemetry.py::command_span, packages/mcp/src/mintmory/mcp/history_server.py::main, packages/mcp/src/mintmory/mcp/server.py::main
Tests: packages.mcp.tests.test_telemetry_mcp::test_verified_fastmcp_version_is_installed

`accept: <why>` counts these on the evidence of the real run: the next run does the red step again, and when the check cannot decide again, the claim is taken (the verifier and the judge see that it was accepted). A criterion that the check shows not to discriminate still fails the attempt.
`retry: <note>` runs the check again, for example after an L4 upgrade; the note reaches the agent.
A person answers; an agent only where `clarifier.answer_by_agents` is true on the base branch.

### Options
1. accept: count these on the evidence of the real run
2. retry: run the check again (after an L4 upgrade or a fix)

### Answer
<!-- write below this line -->
accept: C-7d4fc8c6 is a dependency pin by its own text (a test asserts importlib.metadata.version("fastmcp") == "3.4.2"); uv.lock pins fastmcp 3.4.2 and the real run passed, so the zero-value check cannot judge it by nature. The other criteria of 3.1 stay under the check.

---

## Q-003: Task 3.1: the pre-satisfied check could not decide

- **Status:** answered
- **Blocking tasks:** 3.1
- **Kind:** harness
- **Asked:** 2026-10-18T16:14Z by deepseek, run r-20261018T1601Z-d1c5, task 3.1
- **Criteria:** C-7d4fc8c6 (observability › MCP tool calls are traced once › The verified FastMCP version is installed)

### Context
L4 could not run the pre-satisfied check of task 3.1, so it does not count the failure against the agent: no attempt was used and no profile was escalated.
Why: its tests import no project module: the zero-value check cannot judge them
Runs: test-presatisfied, test-base-run
Kept real: nothing
Tests: packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one

`accept: <why>` counts these on the evidence of the real run: the next run does the red step again, and when the check cannot decide again, the claim is taken (the verifier and the judge see that it was accepted). A criterion that the check shows not to discriminate still fails the attempt.
`retry: <note>` runs the check again, for example after an L4 upgrade; the note reaches the agent.
A person answers; an agent only where `clarifier.answer_by_agents` is true on the base branch.

### Options
1. accept: count these on the evidence of the real run
2. retry: run the check again (after an L4 upgrade or a fix)

### Answer
<!-- write below this line -->
retry: name the FastMCP version test exactly test_fastmcp_version_is_the_verified_one and keep it as: assert importlib.metadata.version("fastmcp") == "3.4.2", with a message that the facts were verified on 3.4.2 only. Keep that name and body in every later step of task 3.1: the owner's accept of this check is bound to that test id.

---

## Q-004: Task 3.1: the pre-satisfied check could not decide

- **Status:** answered
- **Blocking tasks:** 3.1
- **Kind:** harness
- **Asked:** 2026-10-18T16:30Z by deepseek, run r-20261018T1618Z-6c11, task 3.1
- **Criteria:** C-7d4fc8c6 (observability › MCP tool calls are traced once › The verified FastMCP version is installed)

### Context
L4 could not run the pre-satisfied check of task 3.1, so it does not count the failure against the agent: no attempt was used and no profile was escalated.
Why: its tests import no project module: the zero-value check cannot judge them
Runs: test-presatisfied, test-presatisfied, test-base-run
Kept real: packages/api/src/mintmory/api/app.py::main, packages/core/src/mintmory/core/telemetry.py::traced, packages/core/src/mintmory/core/telemetry.py::timed_phase, packages/core/src/mintmory/core/telemetry.py::counts_added, packages/core/src/mintmory/core/telemetry.py::command_span, packages/mcp/src/mintmory/mcp/history_server.py::main, packages/mcp/src/mintmory/mcp/server.py::main
Tests: packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one

`accept: <why>` counts these on the evidence of the real run: the next run does the red step again, and when the check cannot decide again, the claim is taken (the verifier and the judge see that it was accepted). A criterion that the check shows not to discriminate still fails the attempt.
`retry: <note>` runs the check again, for example after an L4 upgrade; the note reaches the agent.
A person answers; an agent only where `clarifier.answer_by_agents` is true on the base branch.

### Options
1. accept: count these on the evidence of the real run
2. retry: run the check again (after an L4 upgrade or a fix)

### Answer
<!-- write below this line -->
accept: C-7d4fc8c6 is a dependency pin by its own text (a test asserts importlib.metadata.version("fastmcp") == "3.4.2"); uv.lock pins fastmcp 3.4.2 and the real run passed, so the zero-value check cannot judge it by nature. This accept covers test_fastmcp_version_is_the_verified_one: keep that test name and body.

---

## Q-005: Task 3.2: the pre-satisfied check could not decide

- **Status:** answered
- **Blocking tasks:** 3.2
- **Kind:** harness
- **Asked:** 2026-10-18T17:12Z by deepseek, run r-20261018T1632Z-40bf, task 3.2
- **Criteria:** C-7d4fc8c6 (observability › MCP tool calls are traced once › The verified FastMCP version is installed)

### Context
L4 could not run the pre-satisfied check of task 3.2, so it does not count the failure against the agent: no attempt was used and no profile was escalated.
Why: its tests import no project module: the zero-value check cannot judge them
Runs: test-presatisfied, test-base-run
Kept real: nothing
Tests: packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one

`accept: <why>` counts these on the evidence of the real run: the next run does the red step again, and when the check cannot decide again, the claim is taken (the verifier and the judge see that it was accepted). A criterion that the check shows not to discriminate still fails the attempt.
`retry: <note>` runs the check again, for example after an L4 upgrade; the note reaches the agent.
A person answers; an agent only where `clarifier.answer_by_agents` is true on the base branch.

### Options
1. accept: count these on the evidence of the real run
2. retry: run the check again (after an L4 upgrade or a fix)

### Answer
<!-- write below this line -->
accept: same dependency pin as Q-004 (task 3.1): test_fastmcp_version_is_the_verified_one, committed in packages/mcp/tests/test_telemetry_mcp.py, asserts importlib.metadata.version("fastmcp") == "3.4.2" exactly as the criterion says; uv.lock pins 3.4.2. Keep that test unchanged.

---

## Q-006: packages/core/tests/test_telemetry_embedder_network.py:153 — frozen OpenAI stub rejects the extra_headers the spec requires

- **Status:** open
- **Blocking tasks:** 4.1
- **Kind:** technical
- **Asked:** 2026-10-18T17:35Z by deepseek, run r-20261018T1715Z-2ba2, task 4.1

### Context
The observability spec 'Outbound calls carry the trace context' (task 4.3) requires OpenAIEmbedder to call self._client.embeddings.create(input=..., model=..., extra_headers=telemetry.inject_trace_headers({})), and the new red test packages/core/tests/test_telemetry_outbound.py::test_embedding_endpoints_receive_the_embed_span_traceparent asserts that exact keyword is passed (it reads kwargs['extra_headers']). The previously-passing test packages/core/tests/test_telemetry_embedder_network.py::test_openai_embed_names_provider_and_model uses _StubEmbeddings.create(self, *, input: list[str], model: str) at line 153, which does not accept the keyword, so it now raises EmbeddingError: ... unexpected keyword argument 'extra_headers'. The two test stubs are mutually incompatible with a single unconditional call, and I may not edit the frozen test; making the red criterion pass while keeping every previously-passing test green needs the frozen stub to accept the keyword.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_telemetry_embedder_network.py`, `packages/core/tests/test_telemetry_outbound.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit add-telemetry-boundary-tracing`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_telemetry_embedder_network.py`: change line 153 to `def create(self, *, input: list[str], model: str, **kwargs: Any) -> _StubEmbeddingResponse:`
2. Edit `packages/core/tests/test_telemetry_embedder_network.py`: change line 153 to `def create(self, *, input: list[str], model: str, extra_headers: Any = None) -> _StubEmbeddingResponse:`

### Clarifier suggestion
Edit `packages/core/tests/test_telemetry_embedder_network.py`: change line 153 to `def create(self, *, input: list[str], model: str, **kwargs: Any) -> _StubEmbeddingResponse:`

### Answer
<!-- write below this line -->
