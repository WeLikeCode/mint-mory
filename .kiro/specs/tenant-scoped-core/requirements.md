# Requirements — Multi-Tenancy 4/10: tenant-scoped dreaming and core functions

> **Depends on:** `multi-tenancy` (errors, `TENANT_GLOBAL`, `get_summary(concept,
> tenant_id="global")`, `get_tenant`, `list_tenants`), `multi-tenancy-writes`
> (write guard, `CrossTenantLinkError` on `add_link`, `tenant_id` on
> `archive_memory` / `supersede_memory` / `apply_feedback`, the equal-tenant rule
> of `update_memory(…, tenant_id=…)`) and `multi-tenancy-reads` (the
> `tenant_id` parameter of every read). Changes `dreaming.py`, `llm.py`,
> `notes.py`, `vision.py`, `session.py`, `cochange.py`, the dream and summary
> paths of the MCP server, the CLI and the HTTP API, and the API error mapping.
> Adds no tenant selector to any transport.

## Introduction

The storage layer can now confine reads and refuses cross-tenant references.
This unit makes the core consumers tenant-aware so that, once a second tenant
exists, nothing mixes tenants: dreaming runs per tenant, and notes, image
descriptions, summaries and feedback stay inside one tenant. The selectors
(`--tenant`, the MCP scope) arrive in `multi-tenancy-cli` and
`tenant-scoped-mcp`; here every transport keeps today's global behaviour, made
safe for a multi-tenant database.

### The write-tenant rule (used by this and the later units)

- A **create** (memory, note, link, summary, image description, session) is
  stamped with one concrete write tenant `W`, and every record it references is
  already in `W`.
- A read whose result decides what a create references — note anchoring,
  dreaming steps, summary-job and image-job collection — is confined to `W`,
  `global` included.
- A **modification** of an existing record by id (update, archive, feedback
  scores) acts on the stored row in its own tenant and never changes it.
- The global scope (HTTP API, MCP global scope, CLI without `--tenant`) uses
  `W = "global"`; a named scope `T` uses `W = T`.

## Requirements

### Requirement 1 — Tenant-scoped `DreamingEngine`

#### Acceptance Criteria

1. `DreamingEngine.__init__(self, adapter, summarizer=None,
   conflict_resolver=None, link_settings=None, summary_settings=None, *,
   tenant_id: str | None = None)` SHALL store `self.tenant_id`.
2. WHEN `tenant_id` is a concrete `T` THEN every adapter read of every step
   (`list_active_memory_ids`, `get_memory`, `get_existing_relates_to_pairs`, the
   three `get_anomaly_*` helpers, `get_flagged_memories`,
   `get_stale_archivable_ids`, `get_rehabilitable_rows`) SHALL pass
   `tenant_id=T`; `get_summary(concept, T)`; every write SHALL be confined to
   `T`: `add_link(ConceptLink(…, tenant_id=T))`,
   `upsert_summary(MemorySummary(…, tenant_id=T))`, `update_memory(mid,
   tenant_id=T, …)` (a non-`T` row raises `TenantImmutableError` instead of being
   changed), `archive_memory(mid, tenant_id=T)`, `supersede_memory(a, by_id=b,
   tenant_id=T)`, and the resolution `ADD` uses `add_memory(…, tenant_id=T)`.
3. A `contradicts_ids` entry of another tenant SHALL resolve to `None` through
   `get_memory(other, tenant_id=T)` and be skipped: no cross-tenant resolution.
4. `collect_summary_jobs` and `apply_summary` SHALL use the engine's tenant: the
   jobs list only `T`'s concepts and contents, `apply_summary` stamps `T` and
   counts `memory_count` over `T`'s active memories.
5. `tenant_id=None` SHALL be today's engine (reads unscoped, writes stamped
   `global`). It is kept for existing direct callers; on a database with more
   than one tenant it can attempt a cross-tenant link, which `add_link` rejects,
   so no transport uses it after this unit (R3).
6. `build_dreaming_engine(adapter, llm_settings=None, link_settings=None,
   summary_settings=None, *, tenant_id: str | None = None)` SHALL pass
   `tenant_id` to the engine and to `build_conflict_resolver(settings, adapter,
   *, tenant_id: str | None = None)`, whose lookups become `adapter.get_memory(cid,
   tenant_id=tenant_id)`.
7. Scenario A (linking and summaries), default `LinkSettings()` (a pair links
   when it shares ≥ 1 entity) and `SummarySettings()` (`min_memories = 3`), no
   conflict resolver, summarizer `lambda concept, contents:
   f"{concept}:{len(contents)}"`, memories added with `add_memory` so
   `entity_ids` come from `extract_entities` (verified: "Alice works at Acme" →
   `["alice", "acme"]`): `global` holds g1 "Alice works at Acme" and g2 "Bob
   works at Acme"; `t1` holds a1 "Alice works at Acme", a2 "Carol works at Acme",
   a3 "Dan works at Acme". `DreamingEngine(store, summarizer=…,
   tenant_id="t1").run_light()` SHALL create exactly three `relates_to` links
   (a1–a2, a1–a3, a2–a3), all with `tenant_id == "t1"`, and exactly one summary
   (`concept == "acme"`, `summary_text == "acme:3"`, `tenant_id == "t1"`); no
   link touches g1 or g2 and `global` has no summary; a second run reports
   `new_links == 0` and `new_summaries == 0`.
8. Scenario B (resolution, discriminating; a separate database with tenants
   `global` and `t1`): `t1` holds a note n1 ("Acme is
   closed on Fridays", `is_note=True`, `flagged_for_review=True`,
   `contradicts_ids=["g9", "a9"]`), a9 "Acme opens on Fridays" (`t1`) and g9
   "Acme opens on Fridays" (`global`). `DreamingEngine(store,
   tenant_id="t1").run_full()` SHALL supersede a9 by n1 (`a9.superseded_by ==
   n1`, archived) and leave g9 active with `superseded_by is None`. (An unscoped
   lookup would pick g9 first and the cross-tenant `supersede_memory` would
   raise.)

### Requirement 2 — Per-tenant dreaming entry points (`dreaming.py`)

#### Acceptance Criteria

1. `dreaming.py` SHALL define (with `from pydantic import BaseModel, Field`):

   ```python
   EngineFactory = Callable[[str], DreamingEngine]

   class DreamAllReport(BaseModel):
       intensity: DreamIntensity
       per_tenant: dict[str, DreamReport] = Field(default_factory=dict)
       skipped_inactive: list[str] = Field(default_factory=list)
       failed: dict[str, str] = Field(default_factory=dict)  # id -> "ExcType: message"
       def total(self) -> DreamReport: ...

   class DreamFailedError(RuntimeError):
       def __init__(self, failed: dict[str, str]) -> None: ...

   def dream_all_tenants(adapter: StorageBackend, *, intensity: DreamIntensity,
                         engine_factory: EngineFactory) -> DreamAllReport: ...
   def run_dream(adapter: StorageBackend, *, intensity: DreamIntensity,
                 tenant_id: str | None, engine_factory: EngineFactory) -> DreamReport: ...
   ```

   `DreamAllReport` is not in `types.py`: it is neither stored nor served by the
   HTTP API, so `schema.sql` and the OpenAPI document do not change.
2. `dream_all_tenants` SHALL iterate `adapter.list_tenants()` (ordered by id): an
   inactive tenant goes to `skipped_inactive` (dreaming writes; inactive is
   read-only); otherwise `engine_factory(t.id)` runs `run_full()` for
   `DreamIntensity.FULL` and `run_light()` otherwise, into `per_tenant[t.id]`;
   an `Exception` from one tenant is recorded as `failed[t.id] =
   f"{type(exc).__name__}: {exc}"` and the loop continues. Writes that tenant's
   pass made before the exception are not rolled back (dreaming steps are not
   transactional; every step is idempotent, so the next run completes them).
3. `total()` SHALL return a `DreamReport` whose `intensity` is the report's, whose
   `duration_ms`, `new_links`, `new_summaries`, `contradictions_resolved`,
   `memories_archived` and `memories_rehabilitated` are the sums over
   `per_tenant`, and whose `anomalies` is an `AnomalyReport` with
   `high_staleness_useful`, `never_accessed` and `contradictions` each
   concatenated in tenant-id order (a report without entries gives zeros and
   `AnomalyReport()`).
4. `DreamFailedError(failed)` SHALL have the message `"dreaming failed for
   tenant(s): " + ", ".join(f"{t} ({failed[t]})" for t in sorted(failed))` — for
   example `dreaming failed for tenant(s): t1 (RuntimeError: boom), t2
   (ValueError: bad)` — and keep `failed`.
5. `run_dream` with a concrete `tenant_id` SHALL raise `TenantNotFoundError` for
   an unknown tenant and `TenantInactiveError` for an inactive one before
   running, and otherwise return that tenant's report. With `tenant_id=None` it
   SHALL call `dream_all_tenants`, raise `DreamFailedError(report.failed)` when
   any tenant failed, and otherwise return `report.total()`.
6. One-tenant parity: on a database whose only tenant is `global`,
   `run_dream(…, tenant_id=None)` SHALL produce the same mutations and the same
   `DreamReport` counters (every field except `duration_ms`) as today's
   `DreamingEngine(adapter).run_light()` / `run_full()`. Test: two database files
   built from the same seed with explicit ids — p1..p3 "Alice/Bob/Carol works at
   Acme"; p4 a note "Acme is closed on Fridays" flagged with `contradicts_ids=["p5"]`
   and p5 "Acme opens on Fridays"; p6 "Old memo" with `is_stale=True`,
   `staleness_score=9.5`, `last_accessed_at=None` (archivable); p7 "Useful tip"
   with `is_stale=True`, `usefulness_score=6.0`, `staleness_score=4.0`,
   `last_accessed_at` = now − 1 day (rehabilitable) — and the Scenario A
   summarizer, no resolver; run `run_full()` of the legacy engine on one and
   `run_dream(…, intensity=DreamIntensity.FULL, tenant_id=None, engine_factory=
   lambda t: DreamingEngine(store, summarizer=…, tenant_id=t))` on the other;
   compare the sets of links `(source, target, link_type, strength)`, summaries
   `(concept, summary_text, memory_count)` and per-memory `(is_active,
   is_archived, is_stale, staleness_score, flagged_for_review, superseded_by)`,
   and the report counters.
7. Multi-tenant: with tenants `global`, `t1` (active) and `t2` (inactive),
   `dream_all_tenants` returns `per_tenant` keys `["global", "t1"]` and
   `skipped_inactive == ["t2"]`; an engine factory that raises for `t1` gives
   `failed == {"t1": "RuntimeError: boom"}` and `global` still dreamed;
   `run_dream(…, tenant_id=None)` then raises `DreamFailedError`.

### Requirement 3 — Every transport dreams per tenant

#### Acceptance Criteria

1. MCP `memory_dream(intensity="light")` (`packages/mcp/src/mintmory/mcp/server.py`),
   CLI `dream [--full/--light]` (`packages/cli/src/mintmory/cli/main.py`) and
   HTTP `POST /dream` (`packages/api/src/mintmory/api/app.py`, whose route
   function is itself named `run_dream`, so it imports the core function as
   `from mintmory.core.dreaming import run_dream as run_tenant_dreams`) SHALL call
   `run_dream(store, intensity=…, tenant_id=None, engine_factory=…)`; MCP and CLI
   build engines with
   `build_dreaming_engine(store, settings.llm, link_settings=settings.link,
   summary_settings=settings.summary, tenant_id=t)`, the API with
   `DreamingEngine(store, tenant_id=t)` (as today, no LLM).
2. The return shape SHALL stay a `DreamReport` in every transport (MCP JSON,
   CLI table, API `response_model=DreamReport`): for the global scope it is the
   per-tenant total. `multi-tenancy-cli` and `tenant-scoped-mcp` add the named
   scope later with the same function.
3. `DreamFailedError` SHALL surface as an MCP tool error (fastmcp `ToolError`
   on the client), a CLI `error: <message>` on stderr with exit code 1, and HTTP
   500 `{"detail": <message>}`. Test seam: monkeypatch
   `mintmory.core.dreaming.DreamingEngine.run_light` to raise
   `RuntimeError("boom")`, so every tenant's pass fails.

### Requirement 4 — Summary and image job paths on the global tenant

#### Acceptance Criteria

1. MCP `summary_jobs` / `summary_put`, CLI `summary-jobs` / `summary-put` and
   HTTP `GET /summaries/jobs` / `PUT /summaries/{concept}` SHALL build their
   engine with `tenant_id=TENANT_GLOBAL`, so on a multi-tenant database they
   work on `global` memories only. On a one-tenant database the output is
   identical to today.
2. The image paths use the `tenant_id="global"` defaults of R5 and need no
   transport change.

### Requirement 5 — Core functions take a tenant

#### Acceptance Criteria

1. `notes.create_note(adapter, content, about=None, when=None, until=None,
   category=None, settings=None, *, tenant_id: str = TENANT_GLOBAL) ->
   NoteResult` SHALL stamp the note with `tenant_id`, call
   `anchor_candidates(about, limit=5, tenant_id=tenant_id)` and create the
   `ANNOTATES` link with `tenant_id`. Example: `global` holds "Tokyo trip plan",
   `t1` holds "Tokyo trip budget"; `create_note(store, "book hotel",
   about="Tokyo trip", tenant_id="t1")` never anchors to the `global` memory.
2. `notes.notes_list(adapter, about=None, upcoming=False, overdue=False, limit=50,
   now=None, *, tenant_id: str | None = None)` SHALL pass `tenant_id` to
   `list_notes`.
3. `vision.image_jobs(adapter, *, include_all=False, include_bytes=False,
   limit=0, settings=None, tenant_id: str = TENANT_GLOBAL)` SHALL list only that
   tenant's image file-records (`list_image_file_records(tenant_id=…)`,
   `get_annotating_descriptions(…, tenant_id=…)`).
4. `vision.image_caption_put(adapter, file_id_or_path, description, *,
   settings=None, tenant_id: str = TENANT_GLOBAL)` SHALL resolve the file-record
   with `get_memory(…, tenant_id=…)` / `find_image_file_record(…, tenant_id=…)`
   (another tenant's file-record raises today's `KeyError` "no active image
   file-record found …"), archive old descriptions with `archive_memory(…,
   tenant_id=…)`, and create the description and its link in `tenant_id`.
   `vision.caption_pending_images(…, tenant_id: str = TENANT_GLOBAL)` SHALL pass
   it to both.
5. `session.apply_feedback(adapter, session_id, useful_ids, stale_ids,
   confidence_rating=None, reasoning=None, *, tenant_id: str | None = None) ->
   QuerySession` SHALL validate everything before the first score change: with a
   concrete `T`, `get_session(session_id, tenant_id=T)` being `None` raises
   `ValueError(f"session {session_id!r} not found")` and an id of `useful_ids +
   stale_ids` that `get_memory(id, tenant_id=T)` does not find raises
   `ValueError(f"memory {id!r} not found")`; with `None` (the session and ids
   looked up unscoped) a missing id raises today's `KeyError(f"memory {id!r} not
   found")`; in both cases an id whose tenant is inactive raises
   `TenantInactiveError(<tenant>)`. Only then are scores applied with
   `apply_feedback(…, tenant_id=tenant_id)`, so a rejected call changes no score.
   (A deactivation racing the loop can still stop it part-way, as today.)
6. `cochange.changed_with(store, path, *, tenant_id: str | None = None)` and
   `cochange.documents_timeline(store, *, since=None, from_iso=None, to_iso=None,
   collection=None, limit=50, tenant_id: str | None = None)` SHALL add `AND
   tenant_id = ?` to every `memories` and `concept_links` SELECT when concrete.
   (Verified: each of these SELECTs reads one table without a join, so the
   unqualified column is unambiguous.)
7. Other create paths stay on the global tenant in this release: `index-tree`
   (manifest, file-records, cochange links), the agent-history ingest and the
   document converters write `global` records and are refused for a named tenant
   by `multi-tenancy-cli`; the only content-dedup caller is CLI `ingest`, which
   `multi-tenancy-cli` confines to its write tenant.
8. The multi-step creates (`create_note`, `image_caption_put`,
   `caption_pending_images`) stay non-atomic, as today: a tenant deactivated
   between their writes stops them with `TenantInactiveError` after the writes
   already made (for example a note without its anchor link).

### Requirement 6 — HTTP API on a multi-tenant database

#### Acceptance Criteria

1. The API SHALL stay on the global tenant with no tenant input: reads unscoped,
   creates stamped `global`. With two tenants, `POST /memories/search` returns
   memories of both.
2. `app.py` SHALL register one exception handler for `TenantError` returning
   `{"detail": str(exc)}` with: `TenantNotFoundError` 404; `TenantInactiveError`,
   `CrossTenantLinkError`, `TenantImmutableError` 409; `ProtectedTenantError`,
   `ScopeRequiredError` 403; `InvalidTenantIdError` 422;
   `TenancyNotSupportedError` 501; `TenantMigrationError` 503.
3. Examples (a1, a2 in `t1`): `POST /memories/a1/links` with target a2 → 409 and
   no link; `DELETE /memories/a1` → 204, a1 archived and still `t1`; `PATCH
   /memories/a1` after `set_tenant_active("t1", False)` → 409.

### Requirement 7 — Gates

#### Acceptance Criteria

1. Every existing test SHALL pass unchanged on a one-tenant database, and the
   `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs Postgres,
   Docker or a network service.
