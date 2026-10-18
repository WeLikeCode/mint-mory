# Requirements — Multi-Tenancy 5/10: CLI tenant selector and tenant commands

> **Depends on:** `tenant-scoped-core` (`run_dream`, the `tenant_id` parameters
> of `create_note`, `notes_list`, `image_jobs`, `image_caption_put`,
> `caption_pending_images`, `changed_with`, `documents_timeline`,
> `build_dreaming_engine`), `multi-tenancy-reads` (`search(…, tenant_id=…)`,
> `get_stats(tenant_id)`, `memory_exists_with_content(content, tenant_id)`),
> `multi-tenancy` (`create_tenant`, `get_tenant`, `list_tenants`,
> `validate_tenant_id`, `TenantError` and subtypes) and `multi-tenancy-writes`
> (the write guard that raises `TenantNotFoundError` / `TenantInactiveError`).
> Changes `packages/cli/src/mintmory/cli/main.py` and CLI tests only.

## Introduction

The CLI is the first transport that selects a tenant. One root option,
`--tenant`, applies to every command of the invocation: absent means the global
scope (reads over every tenant, creates stamped `global`); `--tenant T` confines
reads to `T` and stamps creates with `T`. Two commands manage the tenant
directory. Commands that are not tenant-aware refuse a named tenant instead of
silently running global.

## Requirements

### Requirement 1 — The root `--tenant` option

#### Acceptance Criteria

1. The existing root callback (`@app.callback()`, today `_init_telemetry`) SHALL
   gain `tenant: str | None = typer.Option(None, "--tenant", help=…)`. The option
   goes before the command: `mintmory --tenant acme add "x"`; `mintmory add "x"
   --tenant acme` is Typer's usage error (exit 2).
2. The callback SHALL set a module global `_TENANT: str | None` on every
   invocation: `None` when the option is absent, empty or `global`; otherwise the
   value after `validate_tenant_id` (an invalid value prints `error: invalid
   tenant id 'Bad': …` to stderr and exits 1 before any command runs).
3. Helpers SHALL map it: `_read_tenant() -> str | None` returns `_TENANT`;
   `_write_tenant() -> str` returns `_TENANT or TENANT_GLOBAL`.

### Requirement 2 — Tenant-aware commands

#### Acceptance Criteria

1. These commands SHALL pass `R = _read_tenant()` / `W = _write_tenant()`:

   | Command | Call |
   |---|---|
   | `add` | `add_memory(…, tenant_id=W)` |
   | `ingest` | dedup `memory_exists_with_content(chunk, tenant_id=W)`; `add_memory(…, tenant_id=W)` |
   | `search` | `store.search(request, tenant_id=R)` |
   | `stats` | `get_stats(tenant_id=R)` |
   | `note` | `create_note(…, tenant_id=W)` |
   | `notes` | `notes_list(…, tenant_id=R)` |
   | `summary-jobs`, `summary-put` | `build_dreaming_engine(…, tenant_id=W)` |
   | `image-jobs`, `image-caption-put`, `vision-run` | `tenant_id=W` |
   | `docs timeline`, `docs changed-with` | `tenant_id=R` |
   | `dream [--full/--light]` | `run_dream(store, intensity=…, tenant_id=R, engine_factory=…)` |

2. `dream` without `--tenant` (or with `--tenant global`) SHALL dream every active
   tenant separately and print the per-tenant total; `--tenant T` dreams only `T`.
3. A read confined to a missing tenant SHALL print an empty result and exit 0
   (`mintmory --tenant nope search x` prints `0 result(s)`).

### Requirement 3 — Commands that refuse a named tenant

#### Acceptance Criteria

1. WHEN `_read_tenant()` is not `None` and the invoked command is one of `serve`,
   `mcp-serve`, `doctor`, `index-tree`, `history` (any subcommand) or
   `migrate-storage` THEN the root callback SHALL print `error: '<command>' does
   not support --tenant; run it without --tenant` to stderr and exit 1 before the
   command runs. Without `--tenant` these commands behave as today.
2. The option SHALL have no effect on `tenant create` and `tenant list` (R4):
   the tenant directory is the same in every scope. (`tenant copy`, added by
   `cross-tenant-copy`, refuses a named tenant itself.)

### Requirement 4 — `tenant create` and `tenant list`

#### Acceptance Criteria

1. A `tenant` Typer group SHALL be added with:
   - `tenant create ID [--name NAME]`: calls `create_tenant(ID, NAME or "")`;
     prints `created tenant 'ID'` when `get_tenant(ID)` was `None` before the
     call, else `tenant 'ID' already exists` (the existing row is unchanged);
     exit 0 in both cases; an invalid id prints `error: invalid tenant id …` to
     stderr and exits 1.
   - `tenant list [--json]`: a table with the columns `id`, `name`, `is_active`,
     `created_at`, one row per tenant ordered by id; with `--json`, the output is
     exactly `json.dumps([t.model_dump(mode="json") for t in list_tenants()])`.
2. A fresh database lists exactly `global` (name `Global (default) tenant`).

### Requirement 5 — Errors and exit codes

#### Acceptance Criteria

1. Every command of R2 and R4 SHALL catch `TenantError` (including
   `TenancyNotSupportedError` on the Postgres backend and `TenantMigrationError`
   from `initialise()` in `_get_store()`) and `DreamFailedError`, print `error:
   <str(exc)>` to stderr and exit 1. Other exceptions behave as today.
2. `TenantNotFoundError` / `TenantInactiveError` from a write SHALL leave the
   database unchanged.

### Requirement 6 — Tests (`packages/cli/tests/test_cli_tenancy.py`, CliRunner, the `cli_db` fixture)

#### Acceptance Criteria

1. `tenant create acme --name "Acme Corp"` → exit 0, `created tenant 'acme'`;
   again → `tenant 'acme' already exists`; `tenant create Bad` → exit 1, stderr
   contains `invalid tenant id 'Bad'`; `tenant list --json` → ids `["acme",
   "global"]` with name `Acme Corp` for `acme`.
2. `--tenant acme add "Acme uses Postgres"` stores a row with `tenant_id ==
   "acme"`; `add "Global uses SQLite"` stores `global`; `--tenant acme search
   uses` lists only the Acme row; `search uses` lists both; `--tenant acme
   stats` shows `total_memories` 1.
3. `--tenant nope add x` → exit 1, stderr `tenant 'nope' not found`, no row;
   `--tenant nope search x` → exit 0, `0 result(s)`; after
   `set_tenant_active("acme", False)` (Python API), `--tenant acme add y` → exit
   1 with `is inactive`, while `--tenant acme search uses` still lists the row.
4. `--tenant acme index-tree <dir>` → exit 1 with `does not support --tenant`;
   `--tenant Bad stats` → exit 1 with `invalid tenant id`.
5. With `global` holding "Alice works at Acme" / "Bob works at Acme" and `acme`
   holding "Carol works at Initech" / "Dan works at Initech":
   `--tenant acme dream` creates a link only between the two `acme` memories;
   a following `dream` creates the `global` link; no link joins two tenants.
6. `--tenant acme note "renew contract" --about Initech` stores an `acme` note;
   `--tenant acme notes` lists it; `notes` lists it too (unscoped read); `global`
   memories are never its anchor.
7. An integration test `tests/integration/test_tenancy_cli.py` SHALL run R6.2,
   R6.3 and R6.6 against one real SQLite file in sequence.

### Requirement 7 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%; existing CLI
   tests pass unchanged. No test needs Postgres, Docker or a network service.
