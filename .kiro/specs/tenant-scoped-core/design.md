# Design — Multi-Tenancy 4/10: tenant-scoped dreaming and core functions

## Grounding (base branch, verified)

- `DreamingEngine` (`dreaming.py`) steps call the adapter directly:
  `detect_anomalies` (three `get_anomaly_*`), `create_concept_links`
  (`list_active_memory_ids`, `get_memory`, `get_existing_relates_to_pairs`,
  `add_link`), `generate_summaries` / `collect_summary_jobs` / `apply_summary`
  (`list_active_memory_ids`, `get_memory`, `get_summary`, `upsert_summary`),
  `resolve_contradictions` (`get_flagged_memories`, `get_memory`,
  `supersede_memory`, `update_memory`, and `_apply_resolution`'s
  `archive_memory` / `update_memory` / `add_memory`), `archive_stale`
  (`get_stale_archivable_ids`, `archive_memory`), `rehabilitate`
  (`get_rehabilitable_rows`, `update_memory`).
- `llm.build_dreaming_engine(adapter, llm_settings, link_settings,
  summary_settings)` builds the summarizer and `build_conflict_resolver(settings,
  adapter)`, whose closure calls `adapter.get_memory(cid)`.
- Dream callers: MCP `memory_dream` and CLI `dream` (via
  `build_dreaming_engine`), HTTP `POST /dream` (`DreamingEngine(store)`).
  Summary callers: MCP `summary_jobs`/`summary_put`, CLI `summary-jobs` /
  `summary-put`, HTTP `GET /summaries/jobs` / `PUT /summaries/{concept}`.
- `notes._resolve_anchor` calls `anchor_candidates` and `add_link`;
  `create_note` adds the note first, then anchors, then `update_memory`.
- `vision.image_caption_put` resolves by `get_memory` then
  `find_image_file_record`, archives prior descriptions, adds the new one and
  links it. `caption_pending_images` walks `image_jobs` then calls
  `image_caption_put`.
- `session.apply_feedback` checks the session then calls
  `adapter.apply_feedback` per id, then `update_session_feedback`.
- `cochange.changed_with` / `documents_timeline` take a `SqliteBackend` and use
  `store.connect()` with raw SQL.
- `api/app.py` has no `TenantError` handler (an unhandled exception is a 500).

## Engine

`self.tenant_id` is read in one private helper per direction:

```python
def _rt(self) -> str | None:          # read tenant
    return self.tenant_id
def _wt(self) -> str:                 # write tenant
    return self.tenant_id or TENANT_GLOBAL
```

Reads pass `tenant_id=self._rt()`; `get_summary` uses `self._wt()`; creates
stamp `self._wt()`; id writes pass `tenant_id=self._rt()` (so `None` keeps
today's by-id behaviour). `update_memory` calls add `tenant_id=self._wt()` only
when `self.tenant_id` is set, so the legacy engine's calls are byte-identical to
today.

## Entry points

`run_dream` is the only function transports call. The engine factory keeps
`dreaming.py` free of an import of `llm.py` (which imports `dreaming.py`): MCP and
CLI pass `lambda t: build_dreaming_engine(store, settings.llm,
link_settings=settings.link, summary_settings=settings.summary, tenant_id=t)`,
the API passes `lambda t: DreamingEngine(store, tenant_id=t)` (and imports the
core function as `run_tenant_dreams`, because its route function is already
called `run_dream`).

Why the total and not the aggregate as the transport output: the MCP tool, the
CLI table and the API `response_model` return `DreamReport` today; the total of
per-tenant passes keeps that contract (no consumer breaks when a second tenant
appears) while every pass stays inside one tenant. The per-tenant breakdown
stays available in core as `DreamAllReport`.

On a one-tenant database `run_dream(None)` runs exactly one pass,
`DreamingEngine(tenant_id="global")`, whose reads add `tenant_id = 'global'` —
every row — so its mutations equal the legacy engine's (R2.6).

## Core functions

`create_note` passes its `tenant_id` to `add_memory` (via the record),
`_resolve_anchor(adapter, note_id, about, settings, tenant_id)` and the link.
`image_caption_put` and `caption_pending_images` pass it through every storage
call. `session.apply_feedback` validates all ids before the first
`adapter.apply_feedback`, so a foreign id leaves every score unchanged.
`cochange` appends `AND tenant_id = ?` to its SELECTs when the tenant is
concrete.

## API errors

```python
_TENANT_HTTP: dict[type[TenantError], int] = {
    TenantNotFoundError: 404, TenantInactiveError: 409, CrossTenantLinkError: 409,
    TenantImmutableError: 409, ProtectedTenantError: 403, ScopeRequiredError: 403,
    InvalidTenantIdError: 422, TenancyNotSupportedError: 501, TenantMigrationError: 503,
}
@app.exception_handler(TenantError)
async def _tenant_error(_: Request, exc: TenantError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=_TENANT_HTTP.get(type(exc), 400))
```

`DreamFailedError` gets its own handler (500, `{"detail": …}`).

## Tests

- `packages/core/tests/test_tenancy_dreaming.py`: R1.7 scenario; R2.6 parity on
  two files; R2.7 multi-tenant cases; `total()` sums; `DreamFailedError` message.
- `packages/core/tests/test_tenancy_core_functions.py`: R5 examples
  (note anchoring, image put on a foreign file-record → `KeyError`, feedback with
  a foreign id leaves scores unchanged, cochange confined).
- Transport tests in the existing MCP/CLI/API test files: dream output is still a
  `DreamReport`; with two tenants the dream creates no cross-tenant link;
  `summary_jobs` lists `global` concepts only; the R6.3 API examples;
  `DreamFailedError` surfaces as `ToolError`, exit 1, HTTP 500 (monkeypatch the
  factory to raise).

## Risks

- A step call left unscoped → the R1.7 scenario fails (a link or summary appears
  in the wrong tenant).
- Legacy engine misuse on a multi-tenant database → no transport uses it;
  `add_link` raises `CrossTenantLinkError` instead of writing a bad link.
