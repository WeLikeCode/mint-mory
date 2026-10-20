# Design Document

## Overview

Fix unit 4 of `multi-tenancy-cli`. The verifier found the problems below in `multi-tenancy-cli`; each task of tasks.md names the findings it answers, and bugfix.md says what must change and what must not.

## Findings and Decisions

### F-da38e145: FB-001 not addressed: No packages/cli/tests/conftest.py appears in the diff, so there is no autou...

Severity: major. Chore: a single phase, no red test.

Requested by CiprianSpot, 2026-10-20T20:04:43Z in FB-001 (tests, packages/cli/tests/test_cli_tenancy_root.py:87-96): test_help_documents_the_tenant_option passes in the L4 gates but fails in the repository CI (GitHub Actions run 39482344837, job 'lint · types · tests', step 'Pytest (coverage gate ≥ 80%)': 1 failed, 2277 passed). In GitHub Actions the variable GITHUB_ACTIONS is set, and Typer then forces a colour terminal: typer/rich_utils.py sets FORCE_TERMINAL = True when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, and _get_rich_console() reads FORCE_TERMINAL on every call. The --help output then carries ANSI escape codes, so the plain sentence 'Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant.' is not found in the normalized output. The L4 gates do not pass GITHUB_ACTIONS, which is why they cannot see it. To reproduce in the gates, set typer.rich_utils.FORCE_TERMINAL to True (monkeypatch.setattr) and invoke --help. Fix without changing production code or this test: add packages/cli/tests/conftest.py (new file) with an autouse fixture that sets typer.rich_utils.FORCE_TERMINAL to None for every CLI test (monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None)), so help output is rendered as in the gates (no colour on a non-terminal) whatever...

    @pytest.mark.l4("C-bfe27132")
    def test_help_documents_the_tenant_option(cli_db: Path) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        normalized = " ".join(result.output.split())
        assert (
            "Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant."
            in normalized
