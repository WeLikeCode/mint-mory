# Design — Multi-Tenancy 3/10: tenant-scoped reads and search

## Grounding (base branch + units 1–2)

- `SqliteBackend.search` computes three score dicts (`_fts_scores`,
  `_trigram_scores`, `_vector_scores`, each a single SELECT) and calls
  `hybrid_search.fuse_and_search` with callables for loading, traversal, note
  auto-include, session recording and retrieval bumping. `PostgresBackend`
  calls the same `fuse_and_search`, so its new keyword parameters default to
  today's behaviour.
- `anchor_candidates` reuses the three score phases with `fuse_and_rank` (no
  session, no bump).
- `search_around` runs one SELECT on `concept_links` per hop.
- All dreaming helpers are single SELECTs relocated from `dreaming.py`.
- `_passes_filter(mem, filt, include_archived)` is the shared post-filter; this
  unit does not change it.

## SQL construction

Each read builds its SQL as today and appends the predicate only for a concrete
tenant:

```python
sql = "SELECT id FROM memories WHERE is_active = 1 AND is_archived = 0"
params: list[Any] = []
if tenant_id is not None:
    sql += " AND tenant_id = ?"
    params.append(tenant_id)
if ordered:
    sql += " ORDER BY id"
```

For the FTS and trigram joins the predicate is `AND m.tenant_id = ?` before
`ORDER BY rank`; for the vector scan `AND tenant_id = ?` after `embedding IS NOT
NULL`; for `_load_memories` `AND tenant_id = ?` after the `IN (…)`; for
`get_annotating_notes` / `get_annotating_descriptions` `AND m.tenant_id = ?`;
for `get_stats` each of the seven statements gets its own predicate. Because the
`None` branch appends nothing, today's SQL text is reproduced exactly, which the
R2.2 trace test checks.

## Search

```python
def search(self, request, query_embedding=None, *, tenant_id=None):
    pool = max(request.limit * 5, 50)
    fts, tri, vec = collect_scores(
        fts_fn=lambda: self._fts_scores(request.query, pool, tenant_id), …)
    t = self.get_tenant(tenant_id) if tenant_id is not None else None
    return fuse_and_search(
        request=request, …,
        load_memories_fn=lambda ids: self._load_memories(ids, tenant_id),
        search_around_fn=lambda a, s: self.search_around(a, s, tenant_id),
        get_annotating_notes_fn=lambda mid, cap: self.get_annotating_notes(mid, cap, tenant_id),
        tenant_id=tenant_id,
        record_session=tenant_id is None or (t is not None and t.is_active),
        …)
```

`fuse_and_search` stamps the session with `tenant_id or "global"`, which
satisfies the `record_query_results` rule of `multi-tenancy-writes`: a confined
search records a session of its own tenant whose results are all that tenant's
memories; an unscoped search records a `global` read-audit session. Skipping the
side effects for an inactive or missing tenant (R3.3–R3.4) is the "read
succeeds, incidental write suppressed" rule; `session_id = ""` tells the caller
there is no session to send feedback for.

## `list_memories`

Filtering happens in Python with the same `_passes_filter` the search uses, so a
`MemoryFilter` means the same thing everywhere. The SQL prefilters on
`is_archived = 0` and the tenant; `limit` applies after filtering so it counts
matching rows. The copy asks for `limit = COPY_MAX + 1` to detect an oversized
selection without loading the whole table twice.

## Postgres interim

Every Postgres read gains the parameter and calls
`_require_global_tenant(tenant_id, "<method>")` first. `list_memories` is a stub
that always raises `TenancyNotSupportedError` (no new Postgres SQL in this unit;
`multi-tenancy-postgres-reads` implements it).

## Tests (`packages/core/tests/test_tenancy_reads.py`, SQLite)

- Seed: tenants `global` and `t1`; per tenant, two memories sharing an entity, a
  `relates_to` link between them, a note annotating one of them, a summary, a
  session, an image file-record (`metadata={"ext": ".png", "path": "/x.png",
  "rel": "x.png"}`), a flagged memory and a stale memory.
- For each R1.1 method: `"t1"` returns only `t1` rows, `None` returns both
  tenants' rows, `"nope"` returns empty.
- R2.2 trace test; R3.6 search examples; R3.7 foreign anchor; R4.2 examples.
- Postgres stub test of R5.3.

## Risks

- A read that forgets the predicate → the per-method three-way test (`t1`,
  `None`, `nope`) catches it.
- A callable passed to `fuse_and_search` without the tenant → the defense-in-depth
  drop of R3.2 plus the search examples.
