# Feedback — multi-tenancy-cli

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | taken | tests | packages/cli/tests/test_cli_tenancy_root.py:87 | CLI help tests must not depend on terminal colour (repository CI fails) |
<!-- l4:feedback-index:end -->

---

## FB-001: CLI help tests must not depend on terminal colour (repository CI fails)

- **Status:** taken
- **Kind:** tests
- **Where:** `packages/cli/tests/test_cli_tenancy_root.py:87-96`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-20T20:04:43Z

### Code
```python
@pytest.mark.l4("C-bfe27132")
def test_help_documents_the_tenant_option(cli_db: Path) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.split())
    assert (
        "Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant."
        in normalized
```

### Feedback
test_help_documents_the_tenant_option passes in the L4 gates but fails in the repository CI (GitHub Actions run 39482344837, job 'lint · types · tests', step 'Pytest (coverage gate ≥ 80%)': 1 failed, 2277 passed). In GitHub Actions the variable GITHUB_ACTIONS is set, and Typer then forces a colour terminal: typer/rich_utils.py sets FORCE_TERMINAL = True when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, and _get_rich_console() reads FORCE_TERMINAL on every call. The --help output then carries ANSI escape codes, so the plain sentence 'Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant.' is not found in the normalized output. The L4 gates do not pass GITHUB_ACTIONS, which is why they cannot see it. To reproduce in the gates, set typer.rich_utils.FORCE_TERMINAL to True (monkeypatch.setattr) and invoke --help. Fix without changing production code or this test: add packages/cli/tests/conftest.py (new file) with an autouse fixture that sets typer.rich_utils.FORCE_TERMINAL to None for every CLI test (monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None)), so help output is rendered as in the gates (no colour on a non-terminal) whatever the environment; and add one test in a new file that sets FORCE_TERMINAL to True, applies the same reset, and asserts the --help output contains no ANSI escape (\x1b[) and does contain the sentence above. Every CLI test, including test_help_documents_the_tenant_option, must pass both with and without GITHUB_ACTIONS=true in the environment.

### Outcome
<!-- written by the harness -->
Taken in round 7 into multi-tenancy-cli-fix-4
