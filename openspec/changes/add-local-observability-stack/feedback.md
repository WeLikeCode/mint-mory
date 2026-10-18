# Feedback — add-local-observability-stack

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | taken | tests | tests/integration/test_helm_telemetry.py:121 | Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...) |
<!-- l4:feedback-index:end -->

---

## FB-001: Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...)

- **Status:** taken
- **Kind:** tests
- **Where:** `tests/integration/test_helm_telemetry.py:121-131`
- **Where:** `tests/integration/test_observability_stack.py:197-199`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T19:51:33Z

### Code
`tests/integration/test_helm_telemetry.py:121-131`
```python
@pytest.mark.l4("C-7836148e")
@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_helm_template_defaults_disable_telemetry() -> None:
    output = _helm_template()
    assert 'MINTMORY_OTEL_ENABLED: "false"' in output
    assert "OTEL_TRACES_SAMPLER" not in output


@pytest.mark.l4("C-7836148e")
@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_helm_template_renders_sampler_values() -> None:
```
`tests/integration/test_observability_stack.py:197-199`
```python
@pytest.mark.l4("C-d797e1ac")
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
def test_docker_compose_config_accepts_the_stack() -> None:
```

### Feedback
Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...) markers and keep the tests as they are. helm and docker are on the gate runner: the gates already ran these three tests and they passed (the skipped count stayed 114). L4's integrity check refuses any added skip or xfail marker (blocker F-5758ac1b), whatever the spec text says; the spec's 'skipped otherwise' note is outdated.

### Outcome
<!-- written by the harness -->
Taken in round 3 into add-local-observability-stack-fix-2
