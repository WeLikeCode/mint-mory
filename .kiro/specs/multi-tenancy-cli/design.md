# Design — Multi-Tenancy 5/10: CLI tenant selector and tenant commands

## Grounding (base branch, verified)

- `packages/cli/src/mintmory/cli/main.py`: `app = typer.Typer(name="mintmory")`
  with one root `@app.callback()` (`_init_telemetry(ctx)`, which skips telemetry
  for `serve` / `mcp-serve` using `ctx.invoked_subcommand`); `_get_store()` builds
  the store from settings and calls `initialise()`; sub-groups `history` and
  `docs` via `app.add_typer`.
- Commands today: `add`, `search`, `dream`, `stats`, `serve`, `ingest`, `doctor`,
  `index-tree`, `note`, `notes`, `summary-jobs`, `summary-put`, `image-jobs`,
  `image-caption-put`, `vision-run`, `mcp-serve`, `history …`, `docs timeline`,
  `docs changed-with`, `migrate-storage`. There is no `get`, `link`,
  `feedback` or `archive` command, so none is wired here.
- Tests use `typer.testing.CliRunner` with the `cli_db` fixture
  (`MINTMORY_DB=<tmp>/cli_test.db`).

## Root option

```python
_TENANT: str | None = None
_NO_TENANT_COMMANDS = {"serve", "mcp-serve", "doctor", "index-tree", "history", "migrate-storage"}

@app.callback()
def _init_telemetry(ctx: typer.Context,
                    tenant: str | None = typer.Option(None, "--tenant", help="Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant.")) -> None:
    global _TENANT
    _TENANT = None
    if tenant and tenant != TENANT_GLOBAL:
        try:
            _TENANT = validate_tenant_id(tenant)
        except InvalidTenantIdError as exc:
            _fail(exc)
    if _TENANT is not None and ctx.invoked_subcommand in _NO_TENANT_COMMANDS:
        _fail_text(f"'{ctx.invoked_subcommand}' does not support --tenant; run it without --tenant")
    … # existing telemetry init unchanged
```

Resetting `_TENANT` on every callback keeps `CliRunner` invocations in one test
process independent. `_fail(exc: Exception) -> NoReturn` prints `error: {exc}`
with `typer.echo(…, err=True)` and raises `typer.Exit(code=1)`;
`_fail_text(message: str) -> NoReturn` does the same for a plain message.

Errors: a context manager `_tenant_errors()` wraps the body of each command of
R2/R4 and the `initialise()` call in `_get_store()`:

```python
@contextmanager
def _tenant_errors() -> Iterator[None]:
    try:
        yield
    except (TenantError, DreamFailedError) as exc:
        _fail(exc)
```

## Dream

`dream` calls `run_dream(store, intensity=…, tenant_id=_read_tenant(),
engine_factory=lambda t: build_dreaming_engine(store, settings.llm,
link_settings=settings.link, summary_settings=settings.summary, tenant_id=t))` and
renders the returned `DreamReport` in today's table.

## Tenant group

```python
tenant_app = typer.Typer(name="tenant", help="Tenant directory commands")
app.add_typer(tenant_app)

@tenant_app.command("create")
def tenant_create(tenant_id: str = typer.Argument(...), name: str = typer.Option("", "--name")) -> None: …
@tenant_app.command("list")
def tenant_list(as_json: bool = typer.Option(False, "--json")) -> None: …
```

`tenant create` reads `get_tenant` before `create_tenant` only to choose the
message; the write itself is the idempotent `INSERT OR IGNORE` of `multi-tenancy`,
so a race at worst prints "created" twice for one row.

## Why refusal instead of a silent global run

A user who types `mintmory --tenant acme index-tree …` expects `acme` data; the
indexer and the history store are not tenant-aware in this release, so running
them as `global` would put data in the wrong tenant. Exiting 1 with a clear
message is the safe outcome.

## Risks

- A tenant-aware command that forgets `R`/`W` → each row of the R2.1 table has a
  test asserting the stored or returned tenant.
