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
4. The option's help text SHALL say: `Tenant id. Absent or 'global': reads span
   every tenant and writes go to the global tenant.`

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
   (`mintmory --tenant nope search x` prints `0 result(s)`); so do the job lists
   `summary-jobs` and `image-jobs` (they only read, with `W`). Their apply commands
   (`summary-put`, `image-caption-put`, `vision-run`) are writes: a missing or
   inactive tenant exits 1 (R5).

### Requirement 3 — Commands that refuse a named tenant

#### Acceptance Criteria

1. WHEN `_read_tenant()` is not `None` and the invoked command is one of `serve`,
   `mcp-serve`, `doctor`, `index-tree`, `history` (any subcommand) or
   `migrate-storage` THEN the root callback SHALL print `error: '<command>' does
   not support --tenant; run it without --tenant` to stderr and exit 1 before the
   command runs. Without `--tenant` these commands behave as today. (A
   tenant-scoped MCP server is started with `mintmory-mcp --tenant T` or with
   `MINTMORY_MCP_TENANT=T`, which `tenant-scoped-mcp` reads at startup.)
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
   - `tenant list [--json]`: a rich table with the header cells `id`, `name`,
     `is_active`, `created_at`, one row per tenant ordered by id, `is_active`
     printed as `true`/`false` and `created_at` as `isoformat()`; with `--json`,
     the output is exactly `json.dumps([t.model_dump(mode="json") for t in
     list_tenants()])`. Messages use `repr()` of the id (`'acme'`).
2. A fresh database lists exactly `global` (name `Global (default) tenant`).

### Requirement 5 — Errors and exit codes

#### Acceptance Criteria

1. Every command of R2 and R4 SHALL catch, through one helper (`_tenant_errors()`,
   which generalises the `DreamFailedError` handling `tenant-scoped-core` gave
   `dream`), `TenantError` (including
   `TenancyNotSupportedError` on the Postgres backend and `TenantMigrationError`
   from `initialise()` in `_get_store()`) and `DreamFailedError`, print `error:
   <str(exc)>` to stderr and exit 1. Other exceptions behave as today.
2. `TenantNotFoundError` / `TenantInactiveError` from a write SHALL leave the
   database unchanged.

### Requirement 6 — Tests (`packages/cli/tests/test_cli_tenancy.py`, CliRunner, the `cli_db` fixture)

#### Acceptance Criteria
1. Directory: `tenant create acme --name "Acme Corp"` → exit 0, stdout `created
   tenant 'acme'`; again → `tenant 'acme' already exists`; `tenant create Bad` →
   exit 1, stderr contains `invalid tenant id 'Bad'`; `tenant list --json` → ids
   `["acme", "global"]`, `name` `Acme Corp` for `acme`.
2. Each test below starts from a fresh `cli_db` and runs, in order, `tenant create
   acme` then its own steps; `t_acme(id)` reads a row's `tenant_id` with
   `SqliteBackend(cli_db).get_memory(id)`.
3. add/search/stats: `--tenant acme add "Acme uses Postgres"` stores `acme`; `add
   "Global uses SQLite"` stores `global`; `--tenant acme search uses` lists only
   the Acme row; `search uses` lists both; `--tenant acme stats` shows
   `total_memories` 1; `--tenant global stats` prints the same as `stats`.
4. Missing and inactive tenants: `--tenant nope add x` → exit 1, stderr `tenant
   'nope' not found`, no row; `--tenant nope search x` → exit 0, `0 result(s)`;
   after `set_tenant_active("acme", False)` (Python API on the same file) `--tenant
   acme add y` → exit 1 with `is inactive` and `--tenant acme search uses` still
   lists the Acme row.
5. Refusals: `--tenant acme index-tree <tmp dir>` → exit 1 with `does not support
   --tenant`; `--tenant Bad stats` and `--tenant Bad tenant list` → exit 1 with
   `invalid tenant id` (validation runs before any command, R1.2).
6. ingest: a file `a.txt` holding `Acme ingest fact`; `--tenant acme ingest a.txt`
   stores one `acme` row; repeating it stores nothing (dedup within `acme`);
   `ingest a.txt` then stores one `global` row (the `acme` copy does not suppress
   it).
7. note/notes: `global` holds "Initech HQ is in Austin"; `--tenant acme add "Carol
   works at Initech"` and `--tenant acme add "Dan works at Initech"`; `--tenant
   acme note "renew contract" --about Initech` stores a note with `tenant_id ==
   "acme"` whose `ANNOTATES` link, if one was created, targets an `acme` memory and
   never the `global` one; `--tenant acme notes` lists it; `notes` (unscoped) lists
   it too.
8. dream: `acme` holds "Carol works at Initech" and "Dan works at Initech",
   `global` holds "Alice works at Acme" and "Bob works at Acme":
   `--tenant acme dream` creates links only between `acme` memories (the
   Carol–Dan link among them) and none touching a `global` memory; a following
   `dream` adds the Alice–Bob link; no link ever joins two tenants (in the
   integration sequence of R6.13 the same assertions hold over the accumulated
   data).
9. summary-jobs/summary-put: `acme` holds three memories sharing the entity
   `initech` and `global` three sharing `acme`; `--tenant acme summary-jobs
   --json` lists concept `initech` and not `acme`; `--tenant acme summary-put
   initech "Initech summary"` stores a summary with `tenant_id == "acme"`;
   `--tenant nope summary-jobs --json` prints `[]` and exits 0.
10. image-jobs/image-caption-put: an `acme` image file-record added with
    `add_memory(record=MemoryRecord(content="x.png", category="context",
    source="document", tenant_id="acme", metadata={"path": "/tmp/x.png", "rel":
    "x.png", "ext": ".png", "size": 10, "collection": "c"}))`: `--tenant acme
    image-jobs --json` lists its id and `image-jobs --json` does not;
    `--tenant acme image-caption-put <id> "a cat"` stores a description with
    `tenant_id == "acme"`; `image-caption-put <id> "a cat"` (global) exits 1 with
    today's not-found message.
11. vision-run: with `mintmory.core.vision.captioner_from_settings` monkeypatched
    to return a stub object and `mintmory.core.vision.caption_pending_images`
    monkeypatched to record its keyword arguments and return
    `CaptionRunReport()`, `--tenant acme vision-run` exits 0 and the recorded
    `tenant_id` is `"acme"`.
12. docs: two `source="document"` memories with `metadata={"path": …,
    "collection": "c"}` and `valid_from` set, one per tenant; `--tenant acme docs
    timeline` prints the `acme` path and not the `global` one.
13. An integration test `tests/integration/test_tenancy_cli.py` SHALL run R6.3,
    R6.7, R6.8 and then R6.4 (the deactivation last) against one real SQLite
    file, in that order, after `tenant create acme`.

### Requirement 7 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%; existing CLI
   tests pass unchanged. No test needs Postgres, Docker or a network service.
