"""RED tests for task 1 — the root ``--tenant`` option and refusals.

They trace requirement 1.1 (option before the command, usage error after it),
1.2 (``_TENANT`` set from the option; invalid ids rejected before any command),
1.3 (``_read_tenant`` / ``_write_tenant`` mapping), 1.4 (the help text),
3.1 (commands that refuse a named tenant), 3.2 (the tenant directory is the
same in every scope), 5.1 (``TenantError`` / ``DreamFailedError`` rendered as
``error: …`` with exit 1) and 6.5 (the refusal cases).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from mintmory.cli import main as cli_main
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend, StorageAdapter
from mintmory.core.types import TenantMigrationError, TenantNotFoundError
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path."""
    db_path = tmp_path / "cli_tenancy_root.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path


# ---------------------------------------------------------------------------
# 1.1 — the option goes before the command
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-59ce4fbd")
def test_tenant_option_goes_before_the_command(cli_db: Path) -> None:
    before = runner.invoke(app, ["--tenant", "acme", "add", "x"])
    assert before.exit_code == 0, before.output
    assert "Added memory" in before.output

    after = runner.invoke(app, ["add", "y", "--tenant", "acme"])
    assert after.exit_code == 2, after.output


# ---------------------------------------------------------------------------
# 1.2 / 1.3 — the callback sets the module scope, helpers map it
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-81db0c61")
def test_invalid_tenant_is_rejected_before_any_command(cli_db: Path) -> None:
    result = runner.invoke(app, ["--tenant", "Bad", "add", "should-not-exist"])
    assert result.exit_code == 1, result.output
    assert "error: invalid tenant id 'Bad':" in result.stderr

    store = StorageAdapter(str(cli_db))
    store.initialise()
    try:
        assert store.get_stats().total_memories == 0
    finally:
        store.close()


@pytest.mark.l4("C-81db0c61", "C-041d227d")
def test_tenant_scope_maps_absent_empty_global_and_named(cli_db: Path) -> None:
    for args in (["stats"], ["--tenant", "", "stats"], ["--tenant", "global", "stats"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert cli_main._read_tenant() is None
        assert cli_main._write_tenant() == "global"

    scoped = runner.invoke(app, ["--tenant", "acme", "stats"])
    assert scoped.exit_code == 0, scoped.output
    assert cli_main._read_tenant() == "acme"
    assert cli_main._write_tenant() == "acme"


# ---------------------------------------------------------------------------
# 1.4 — help text
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-bfe27132")
def test_help_documents_the_tenant_option(cli_db: Path) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.split())
    assert (
        "Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant."
        in normalized
    )


# ---------------------------------------------------------------------------
# 3.1 / 6.5 — commands that refuse a named tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-20bd1e63")
def test_serve_refuses_a_named_tenant_but_runs_unscoped(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(uvicorn, "run", fake_run)

    refused = runner.invoke(app, ["--tenant", "acme", "serve"])
    assert refused.exit_code == 1, refused.output
    assert "error: 'serve' does not support --tenant; run it without --tenant" in refused.stderr
    assert calls == []

    unscoped = runner.invoke(app, ["serve"])
    assert unscoped.exit_code == 0, unscoped.output
    assert len(calls) == 1


@pytest.mark.l4("C-20bd1e63")
def test_mcp_serve_refuses_a_named_tenant(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mintmory.mcp import server as mcp_server

    called: list[bool] = []

    def fake_main() -> None:
        called.append(True)

    monkeypatch.setattr(mcp_server, "main", fake_main)

    result = runner.invoke(app, ["--tenant", "acme", "mcp-serve"])
    assert result.exit_code == 1, result.output
    assert "error: 'mcp-serve' does not support --tenant; run it without --tenant" in result.stderr
    assert called == []


@pytest.mark.l4("C-20bd1e63")
def test_doctor_refuses_a_named_tenant(cli_db: Path) -> None:
    result = runner.invoke(app, ["--tenant", "acme", "doctor"])
    assert result.exit_code == 1, result.output
    assert "error: 'doctor' does not support --tenant; run it without --tenant" in result.stderr


@pytest.mark.l4("C-20bd1e63")
def test_index_tree_refuses_a_named_tenant(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()

    result = runner.invoke(app, ["--tenant", "acme", "index-tree", str(tree), "--no-cochange"])
    assert result.exit_code == 1, result.output
    assert "error: 'index-tree' does not support --tenant; run it without --tenant" in result.stderr


@pytest.mark.l4("C-20bd1e63")
def test_history_refuses_a_named_tenant(cli_db: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--tenant",
            "acme",
            "history",
            "timeline",
            "--db",
            str(tmp_path / "history.db"),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "error: 'history' does not support --tenant; run it without --tenant" in result.stderr


@pytest.mark.l4("C-20bd1e63")
def test_migrate_storage_refuses_a_named_tenant(cli_db: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--tenant",
            "acme",
            "migrate-storage",
            "--from",
            f"sqlite:{tmp_path / 'missing.db'}",
            "--to",
            "postgres:postgresql://example/db",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1, result.output
    assert (
        "error: 'migrate-storage' does not support --tenant; run it without --tenant"
        in result.stderr
    )


@pytest.mark.l4("C-8fa7e2dd", "C-20bd1e63", "C-81db0c61")
def test_refusals_and_validation_happen_before_the_command(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()

    refused = runner.invoke(app, ["--tenant", "acme", "index-tree", str(tree), "--no-cochange"])
    assert refused.exit_code == 1, refused.output
    assert "does not support --tenant" in refused.stderr

    bad_stats = runner.invoke(app, ["--tenant", "Bad", "stats"])
    assert bad_stats.exit_code == 1, bad_stats.output
    assert "invalid tenant id" in bad_stats.stderr

    bad_list = runner.invoke(app, ["--tenant", "Bad", "tenant", "list"])
    assert bad_list.exit_code == 1, bad_list.output
    assert "invalid tenant id" in bad_list.stderr


# ---------------------------------------------------------------------------
# 3.2 — a valid tenant does not change the tenant directory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7760785e")
def test_valid_tenant_does_not_change_the_tenant_directory(cli_db: Path) -> None:
    created = runner.invoke(app, ["--tenant", "acme", "tenant", "create", "t1"])
    assert created.exit_code == 0, created.output
    assert "created tenant 't1'" in created.output

    unscoped = runner.invoke(app, ["tenant", "list", "--json"])
    assert unscoped.exit_code == 0, unscoped.output
    scoped = runner.invoke(app, ["--tenant", "acme", "tenant", "list", "--json"])
    assert scoped.exit_code == 0, scoped.output
    assert scoped.stdout == unscoped.stdout
    assert "t1" in scoped.stdout


# ---------------------------------------------------------------------------
# 5.1 — TenantError is rendered as ``error: …`` with exit 1
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8e7b8062")
def test_tenant_migration_error_is_reported(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: SqliteBackend) -> None:
        raise TenantMigrationError("boom")

    monkeypatch.setattr(SqliteBackend, "initialise", boom)

    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 1, result.output
    assert "error: tenant migration failed: boom" in result.stderr


@pytest.mark.l4("C-8e7b8062")
def test_tenant_not_found_from_a_write_is_reported(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: SqliteBackend, *args: object, **kwargs: object) -> object:
        raise TenantNotFoundError("acme")

    monkeypatch.setattr(SqliteBackend, "add_memory", boom)

    result = runner.invoke(app, ["--tenant", "acme", "add", "x"])
    assert result.exit_code == 1, result.output
    assert "error: tenant 'acme' not found" in result.stderr
