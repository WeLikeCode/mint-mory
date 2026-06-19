# Design & FROZEN interface contract — `add-agent-supplied-summaries`

Implementers MUST match these signatures, names, return shapes, and behaviours
exactly. Where intuition and this doc disagree, this doc wins. Overarching
invariants:

- **MintMory config ethos:** every default reproduces today's behaviour. The new
  path is additive; flipping nothing changes the existing summary path.
- **One core, three transports:** all domain logic lives in `mintmory.core`;
  MCP / CLI / API are thin wrappers that serialise `types.py` models. The
  transports build the engine the SAME way `memory_dream` does today
  (`build_dreaming_engine`), so the new path inherits `MINTMORY_LINK_*` /
  `MINTMORY_SUMMARY_*` policy.
- **No new runtime dependency. No network in the new core methods. No new
  `LLMProvider`.** `collect_summary_jobs` / `apply_summary` MUST NOT call any
  summarizer/LLM and MUST work with `provider=none` (no backend configured).
- Gates for every package touched: `pytest` (cov ≥ 80), `ruff check`,
  `ruff format --check`, `mypy --strict` (line-length 100).

The load-bearing claim of this change is: **`generate_summaries` is byte-for-byte
equivalent after the refactor.** The existing dreaming tests
(`test_summaries_require_three_memories`, `test_summaries_skipped_without_summarizer`,
`test_summary_top_k_caps_number_of_summaries`, `test_summary_stoplist_concept_not_summarised`,
`test_summary_concurrency_matches_serial_and_is_idempotent`) MUST stay green
**without edits**. Treat any edit to those tests as a contract violation.

---

## 0. Ground truth — today's `generate_summaries` selection (DO NOT CHANGE)

For reference, the selection currently inline in
`DreamingEngine.generate_summaries` (`core/dreaming.py`) is, in order:

1. `ss = self.summary_settings`; `stoplist = self.link_settings.stoplist`.
2. Read all active, non-archived memories **`ORDER BY id`**:
   `SELECT id, content, entity_ids FROM memories WHERE is_active = 1 AND
   is_archived = 0 ORDER BY id`.
3. Build `entity_to_contents: dict[str, list[str]]` (a `defaultdict(list)`): for
   each row, load the full record via `self.adapter.get_memory(row["id"])`, skip
   `None`, and for each `entity` in `mem_record.entity_ids` that is **not** in
   `stoplist`, append `mem_record.content`. (Append order follows the `ORDER BY
   id` row order; an entity appearing twice in one record's `entity_ids` appends
   twice — preserve this exactly.)
4. Select concepts: `[c for c in sorted(entity_to_contents) if
   len(entity_to_contents[c]) >= ss.min_memories]`.
5. `top_k` cap (only when `ss.top_k > 0 and len(concepts) > ss.top_k`):
   `concepts.sort(key=lambda c: (-len(entity_to_contents[c]), c))` then
   `concepts = sorted(concepts[: ss.top_k])`.
6. Build `prepared: list[tuple[str, list[str], int]]` in (sorted) concept order:
   for each concept, `all_contents = entity_to_contents[concept]`;
   `memory_count = len(all_contents)`; `contents = all_contents`; if
   `ss.max_content_chars > 0`: `contents = [c[: ss.max_content_chars] for c in
   contents]`; then `contents = contents[: ss.max_contents]`.

`generate_summaries` then summarises (`prepared` → `summary_texts`, serial or
concurrent) and upserts, with an idempotency skip. **None of that downstream code
changes**; only steps 1–6 (the selection + preparation) move into the shared
helper.

> Subtle invariants the helper MUST preserve, or `generate_summaries` is not
> byte-for-byte equivalent:
> - the `ORDER BY id` scan order and the `get_memory` per-row reload (NOT
>   `entity_ids` straight off the FTS-less row — `generate_summaries` reloads the
>   full record);
> - `memory_count = len(all_contents)` is the count of **contents appended for
>   that concept** (i.e. active non-archived memories that mention the
>   non-stoplisted concept), BEFORE the `max_contents` cap — NOT
>   `len(contents)` and NOT a separate SQL `COUNT`;
> - truncation (`max_content_chars`) happens BEFORE the `max_contents` slice;
> - final concept iteration order is the SORTED concept order (after any `top_k`
>   re-sort + `sorted(...)`).

---

## 1. Core — shared selection helper

### 1a. The frozen return type

The helper returns a list of immutable per-concept records in final (sorted)
concept order. Use a `@dataclass(frozen=True)` named `_SummarySelection`, placed
near `_LinkCandidate` in `core/dreaming.py`:

```python
@dataclass(frozen=True)
class _SummarySelection:
    """One concept selected for summarisation, with summarizer-ready inputs.

    ``memory_count`` is the number of active, non-archived memories that mention
    the (non-stoplisted) concept — i.e. ``len`` of the contents collected for the
    concept BEFORE the ``max_contents`` cap. ``contents`` is the truncated,
    capped list actually fed to a summarizer. ``memory_ids`` are the ids of the
    contributing memories, in the same scan order, capped to ``max_contents``
    (parallel to ``contents``)."""

    concept: str
    contents: list[str]      # truncated to max_content_chars, capped to max_contents
    memory_count: int        # full active count for the concept (pre-cap)
    memory_ids: list[str]    # contributing memory ids, scan order, capped to max_contents
```

> `memory_ids` is NEW data not currently collected by `generate_summaries`. It is
> required by `SummaryJob` (the agent wants to know which memories back the
> concept). Collecting it is additive and MUST NOT change `generate_summaries`'
> behaviour: `generate_summaries` simply ignores the `memory_ids` field. Build
> `memory_ids` in lockstep with `contents` (same append points, same
> `[: max_contents]` slice) so the two lists stay index-aligned.

### 1b. The helper signature

```python
def _select_summary_concepts(self) -> list[_SummarySelection]:
    """Shared concept-selection + content-preparation for L3 summaries.

    Implements the EXACT selection currently inline in ``generate_summaries``
    (see design §0): active non-archived memories scanned ``ORDER BY id`` and
    reloaded via ``get_memory``; per-concept contents collected for every
    non-stoplisted entity; concepts kept when their content count >=
    ``summary_settings.min_memories``; ``top_k`` cap (deterministic tiebreak by
    concept); per-concept ``max_content_chars`` truncation then ``max_contents``
    cap. Returns one ``_SummarySelection`` per kept concept in final sorted
    concept order. Pure read — no writes, no summarizer/LLM call.
    """
```

Implementation MUST mirror §0 steps 1–6 exactly, additionally accumulating a
parallel `ids` list per concept (the contributing `mem_record.id`s) and slicing
it with the same `[: ss.max_contents]` as `contents`.

### 1c. `generate_summaries` after the refactor (behaviour FROZEN)

`generate_summaries` MUST become:

```python
def generate_summaries(self) -> int:
    """... (docstring unchanged in substance) ..."""
    if self.summarizer is None:
        return 0

    ss = self.summary_settings
    prepared = self._select_summary_concepts()

    summarizer = self.summarizer
    if ss.concurrency > 1 and len(prepared) > 1:
        with ThreadPoolExecutor(max_workers=ss.concurrency) as pool:
            summary_texts = list(
                pool.map(lambda sel: summarizer(sel.concept, sel.contents), prepared)
            )
    else:
        summary_texts = [summarizer(sel.concept, sel.contents) for sel in prepared]

    count = 0
    for sel, summary_text in zip(prepared, summary_texts, strict=True):
        existing = self.adapter.get_summary(sel.concept)
        if (
            existing is not None
            and existing.summary_text == summary_text
            and existing.memory_count == sel.memory_count
        ):
            continue
        self.adapter.upsert_summary(
            MemorySummary(
                concept=sel.concept,
                summary_text=summary_text,
                memory_count=sel.memory_count,
            )
        )
        count += 1
    return count
```

The ONLY change vs today is that steps 1–6 are now `prepared =
self._select_summary_concepts()` (a `list[_SummarySelection]`) instead of the
inline `list[tuple[str, list[str], int]]`. The `summarizer is None` early-return,
the concurrency branch (same `ss.concurrency > 1 and len(prepared) > 1` guard),
the idempotency skip (compare `summary_text` AND `memory_count`), the
`upsert_summary` call shape, and the returned `count` are **identical**. The
`max_workers=ss.concurrency` thread pool and the lambda calling
`summarizer(concept, contents)` are preserved; `sel.concept`/`sel.contents` are
the same values that the old tuple carried.

---

## 2. Core — `SummaryJob` (`core/types.py`)

Add ONE model, in the "Dreaming process types" block (next to `AnomalyReport` /
`DreamReport`), matching the existing Pydantic style (no validators needed):

```python
class SummaryJob(BaseModel):
    """A single concept the active agent should summarise (agent-supplied L3).

    Produced by ``DreamingEngine.collect_summary_jobs`` and exposed over the
    transports. The agent writes ``summary_text`` itself (it IS an LLM) and sends
    it back via the apply path — MintMory calls no LLM for this flow.
    """

    concept: str  # the entity/concept name (matches MemorySummary.concept)
    memory_ids: list[str]  # contributing memory ids (scan order, capped to max_contents)
    contents: list[str]  # the memories' content, truncated/capped per summary settings
    memory_count: int  # active non-archived memory count for the concept (pre-cap)
    current_summary: str | None = None  # existing summary_text, if any, so the agent can refine
```

> `memory_ids` and `contents` are **index-parallel** and both reflect the
> `max_contents` cap; `memory_count` is the full pre-cap active count (so the
> agent can tell when it is only seeing a sample). `current_summary` is the
> existing `MemorySummary.summary_text` for the concept (or `None`).

`SummaryJob` is a pure data carrier; it is NOT persisted (only `MemorySummary`
rows are stored).

---

## 3. Core — `collect_summary_jobs`

```python
def collect_summary_jobs(self, include_all: bool = False) -> list[SummaryJob]:
    """Return the L3 concept-summary jobs for the active agent to write.

    Uses the SAME concept selection as ``generate_summaries`` (the shared
    ``_select_summary_concepts`` helper), so the set of candidate concepts and
    their truncated/capped contents are identical to what the configured-LLM path
    would summarise. Does NOT call any summarizer/LLM and does NOT require one
    configured (works with provider=none).

    By DEFAULT (``include_all=False``) returns only concepts that NEED a
    (re)summary — i.e. one of:
      * no current ``MemorySummary`` exists for the concept, OR
      * the stored summary's ``memory_count`` != the concept's current active
        count (the evidence drifted; the summary is out of date).
    With ``include_all=True`` returns one ``SummaryJob`` per qualifying concept
    regardless of existing summaries. Order is the helper's sorted concept order.
    """
    jobs: list[SummaryJob] = []
    for sel in self._select_summary_concepts():
        existing = self.adapter.get_summary(sel.concept)
        if not include_all:
            needs = existing is None or existing.memory_count != sel.memory_count
            if not needs:
                continue
        jobs.append(
            SummaryJob(
                concept=sel.concept,
                memory_ids=sel.memory_ids,
                contents=sel.contents,
                memory_count=sel.memory_count,
                current_summary=existing.summary_text if existing is not None else None,
            )
        )
    return jobs
```

> The needs-resummary rule MUST mirror exactly the idempotency comparison
> `generate_summaries` makes, MINUS the `summary_text` equality (the agent has not
> written text yet): "no current summary OR `memory_count` drift". This is
> intentional — it means after the agent applies a summary for a concept,
> `collect_summary_jobs()` (default) will NOT return that concept again on an
> unchanged DB (the stored `memory_count` now matches), giving the agent a clean
> incremental work-list. Adding/archiving memories that change a concept's active
> count re-surfaces it.
>
> NOTE: the existing `MemorySummary.is_current` flag is NOT consulted by this
> rule (it is never written `False` by the current codebase — see `upsert_summary`
> / `generate_summaries`, which always construct `is_current=True`). Do not add an
> `is_current` term to the needs rule in this change.

`collect_summary_jobs` is independent of `self.summarizer` — it returns jobs even
when `summarizer is None`.

---

## 4. Core — `apply_summary`

```python
def apply_summary(self, concept: str, summary_text: str) -> MemorySummary:
    """Persist an AGENT-SUPPLIED summary for one concept (BYO-LLM L3).

    Builds a ``MemorySummary`` with ``memory_count`` recomputed from the concept's
    CURRENT active count (the same count ``_select_summary_concepts`` would
    report) and ``is_current=True``, ``generated_at`` defaulted to now, then
    persists it via ``adapter.upsert_summary`` (INSERT OR REPLACE keyed on
    ``concept``). Idempotent: re-applying overwrites the concept's summary.

    Calls no summarizer/LLM; works with provider=none. The ``summary_text`` is
    stored verbatim (the agent already produced clean prose — no ``<think>``
    stripping, no prompt). Whitespace is left to the caller.
    """
    memory_count = self._active_count_for_concept(concept)
    return self.adapter.upsert_summary(
        MemorySummary(
            concept=concept,
            summary_text=summary_text,
            memory_count=memory_count,
        )
    )
```

`MemorySummary`'s field defaults already give `is_current=True` and
`generated_at=now` (and a fresh `id`, but `upsert_summary` preserves the existing
row's `id` on conflict), so the constructor above is sufficient — do NOT pass
`is_current`/`generated_at` explicitly.

### 4a. `_active_count_for_concept` — the count helper (FROZEN definition)

`apply_summary` MUST compute `memory_count` with the **same definition** the
selection uses, so a concept the agent just summarised does not immediately
reappear from `collect_summary_jobs()` due to a count mismatch. Add a small
private helper:

```python
def _active_count_for_concept(self, concept: str) -> int:
    """Active, non-archived memory count for one concept, using the SAME rule as
    summary selection: a memory counts iff it is active + non-archived AND its
    ``entity_ids`` contain ``concept`` AND ``concept`` is not in the linking
    stoplist. Returns 0 for a stoplisted concept or one with no active memories.
    """
```

It MUST be consistent with `_select_summary_concepts`: a memory contributes once
**per occurrence** of `concept` in its `entity_ids` (the selection appends once
per non-stoplisted entity occurrence), so the count is "number of contents the
selection would have collected for `concept`". The simplest conformant
implementation reuses the same scan:

```python
    if concept in self.link_settings.stoplist:
        return 0
    conn = self.adapter.connect()
    rows = conn.execute(
        "SELECT id FROM memories WHERE is_active = 1 AND is_archived = 0 ORDER BY id"
    ).fetchall()
    count = 0
    for row in rows:
        mem = self.adapter.get_memory(row["id"])
        if mem is None:
            continue
        count += sum(1 for e in mem.entity_ids if e == concept)
    return count
```

> Rationale for matching "per occurrence" rather than "distinct memory": it must
> equal the `memory_count` that `_select_summary_concepts` produces for the same
> concept, or the incremental rule in §3 breaks (a just-applied summary would show
> a `memory_count` drift and re-surface forever). If `_select_summary_concepts`
> is later changed to dedupe per memory, this helper MUST change in lockstep — but
> NOT in this change. Implementers MAY instead obtain the count by calling
> `_select_summary_concepts()` and reading the matching `sel.memory_count` (and
> `0` if the concept is absent because it is below `min_memories` or stoplisted);
> that is also acceptable and is the most robust against future drift. Whichever
> is chosen, add a test asserting `apply_summary(c, ...)` then
> `collect_summary_jobs()` (default) does NOT return `c` on an unchanged DB.

> Edge case: `apply_summary` accepts ANY `concept` string, even one below
> `min_memories` or absent from the store — it simply records the count
> (possibly 0) and stores the text. It does not validate that the concept appears
> in `collect_summary_jobs`. (A future change could restrict it; not now.)

---

## 5. Transports

All three build the engine **exactly like `memory_dream` does today** —
`build_dreaming_engine(store, settings.llm, link_settings=settings.link,
summary_settings=settings.summary)` — so the new path inherits the same
link/summary policy. The configured LLM tier is irrelevant to these two methods
(they never call the summarizer), but building the engine the same way keeps the
selection policy (`MINTMORY_SUMMARY_*`, stoplist) consistent with `memory_dream`.

### 5a. MCP — `packages/mcp/src/mintmory/mcp/server.py`

Two new `@mcp.tool()`s. Mirror the existing `summary_list` / `summary_get` /
`memory_dream` patterns (thin wrapper, `model_dump(mode="json")`).

```python
@mcp.tool()
def summary_jobs(include_all: bool = False, limit: int = 0) -> list[dict[str, Any]]:
    """List concept-summary jobs for YOU (the agent) to write (agent-supplied L3).

    MintMory does NOT call an LLM for these — you are the LLM. Each job carries the
    concept, the contributing memories' content, the current active memory_count,
    and the existing summary (if any) so you can refine it. Write a concise
    synthesis per concept and send it back with summary_put.

    Args:
        include_all: when False (default), only concepts that NEED a (re)summary
            are returned (no current summary, or the memory_count drifted). When
            True, every qualifying concept is returned.
        limit: max jobs to return (0 = no cap). Applied AFTER selection, in the
            engine's deterministic concept order.

    Returns:
        A list of SummaryJob dicts.
    """
    store = _get_store()
    settings = load_settings()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]
    return [job.model_dump(mode="json") for job in jobs]


@mcp.tool()
def summary_put(concept: str, summary_text: str) -> dict[str, Any]:
    """Store YOUR summary text for a concept (agent-supplied L3 summary).

    Persists summary_text verbatim as the concept's MemorySummary (memory_count
    is recomputed server-side from the current active memories). Idempotent:
    calling again for the same concept overwrites it. No LLM/backend is required.

    Args:
        concept: the concept/entity name (use a concept from summary_jobs).
        summary_text: the synthesis YOU wrote for this concept.

    Returns:
        The stored MemorySummary as a dict.
    """
    store = _get_store()
    settings = load_settings()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    result: dict[str, Any] = engine.apply_summary(concept, summary_text).model_dump(mode="json")
    return result
```

Update the FastMCP `instructions` string: add a sentence such as — "For L3
concept summaries you can supply the text yourself: call summary_jobs to get the
concepts (and their memories) that need summarising, write each summary, and send
it back with summary_put — no separate LLM backend required." (`memory_dream`
still does the configured-LLM path; both coexist.) Also update the tool-map
comment block at the top of the file to list `summary_jobs` / `summary_put`.

### 5b. CLI — `packages/cli/src/mintmory/cli/main.py`

Two new `@app.command()`s. Match the repo's Typer style (the repo uses hyphenated
multi-word commands implicitly via Typer's `_`→`-` conversion, e.g. `mcp_serve`
→ `mcp-serve`; and `index_tree` → `index-tree`). Name the functions
`summary_jobs` and `summary_put` (Typer exposes them as `summary-jobs` /
`summary-put`). Build the engine via `build_dreaming_engine` + the configured
embedder store (`_get_store()`), mirroring `dream`.

```python
@app.command()
def summary_jobs(
    include_all: bool = typer.Option(
        False, "--all/--needed", help="All qualifying concepts vs only those needing a (re)summary"
    ),
    limit: int = typer.Option(0, help="Max jobs (0 = no cap)"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
) -> None:
    """List L3 concept-summary jobs for the agent to write (agent-supplied L3)."""
    from mintmory.core.config import load_settings
    from mintmory.core.llm import build_dreaming_engine

    settings = load_settings()
    store = _get_store()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]

    if json_out:
        import json as _json

        console.print_json(_json.dumps([j.model_dump(mode="json") for j in jobs]))
        return

    table = Table(title="Summary jobs")
    table.add_column("concept", style="cyan", no_wrap=True)
    table.add_column("memories", justify="right", style="green")
    table.add_column("has_summary", style="magenta")
    for j in jobs:
        table.add_row(j.concept, str(j.memory_count), "yes" if j.current_summary else "no")
    console.print(table)
    console.print(f"[dim]{len(jobs)} job(s)[/dim]")


@app.command()
def summary_put(
    concept: str = typer.Argument(..., help="Concept/entity name"),
    text: str | None = typer.Argument(None, help="Summary text (omit to read --file or stdin)"),
    file: Path | None = typer.Option(None, "--file", "-f", help="Read summary text from a file"),
) -> None:
    """Store an agent-supplied summary for a concept (text arg, --file, or stdin)."""
    import sys

    from mintmory.core.config import load_settings
    from mintmory.core.llm import build_dreaming_engine

    if text is not None:
        summary_text = text
    elif file is not None:
        summary_text = file.read_text()
    else:
        summary_text = sys.stdin.read()
    summary_text = summary_text.strip()
    if not summary_text:
        raise typer.BadParameter("empty summary text (provide TEXT, --file, or stdin)")

    settings = load_settings()
    store = _get_store()
    engine = build_dreaming_engine(
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
    )
    summary = engine.apply_summary(concept, summary_text)
    console.print(
        f"[green]Stored summary[/green] for [cyan]{summary.concept}[/cyan] "
        f"[dim]({summary.memory_count} memories)[/dim]"
    )
```

> The text-resolution order is: positional `text` → `--file` → stdin. The
> `summary-put` command strips the resolved text and rejects an empty result.
> `Path` is already imported in `main.py`.

Update the module docstring's command list (top of `main.py`) to include
`mintmory summary-jobs` and `mintmory summary-put`.

### 5c. HTTP API — `packages/api`

One request schema + two routes + OpenAPI YAML. Mirror the existing summaries
routes (`GET /summaries`, `GET /summaries/{concept}`).

`packages/api/src/mintmory/api/schemas.py` — new request body:

```python
class SummaryPut(BaseModel):
    """Request body for ``PUT /summaries/{concept}`` (agent-supplied L3 summary)."""

    summary_text: str = Field(..., min_length=1)
```

`packages/api/src/mintmory/api/app.py` — two routes under the existing
"Summaries" tag. The engine is built via `build_dreaming_engine` (import it),
consistent with the design's "build the engine like `memory_dream`" rule.

> NOTE: the current `POST /dream` route constructs a bare `DreamingEngine(get_store())`
> (no settings) — that is the existing behaviour for `/dream` and is OUT OF SCOPE
> to change here. The two NEW routes MUST use `build_dreaming_engine(...)` with
> loaded settings so selection policy matches MCP/CLI. Add
> `from mintmory.core.config import load_settings` and
> `from mintmory.core.llm import build_dreaming_engine` imports; add `SummaryJob`
> to the core-types import and `SummaryPut` to the schemas import.

```python
@app.get("/summaries/jobs", response_model=list[SummaryJob], tags=["Summaries"])
async def list_summary_jobs(
    include_all: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=0)] = 0,
) -> list[SummaryJob]:
    """Concept-summary jobs for an agent to write (agent-supplied L3).

    ``include_all=false`` (default) returns only concepts needing a (re)summary.
    ``limit=0`` means no cap.
    """
    settings = load_settings()
    engine = build_dreaming_engine(
        get_store(),
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]
    return jobs


@app.put("/summaries/{concept}", response_model=MemorySummary, tags=["Summaries"])
async def put_summary(concept: str, body: SummaryPut) -> MemorySummary:
    """Store an agent-supplied summary for ``concept`` (idempotent upsert)."""
    settings = load_settings()
    engine = build_dreaming_engine(
        get_store(),
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    return engine.apply_summary(concept, body.summary_text)
```

> Route ordering: declare `GET /summaries/jobs` so it is not shadowed by
> `GET /summaries/{concept}`. With FastAPI, a literal path (`/summaries/jobs`)
> and a parametrised one (`/summaries/{concept}`) on different methods do not
> collide for `PUT`; for the two GETs, `jobs` would otherwise match `{concept}` —
> declare the literal `GET /summaries/jobs` route **before** the
> `GET /summaries/{concept}` route in `app.py` to be safe, OR rely on FastAPI's
> "first declared wins" by putting `/summaries/jobs` above. Implementers MUST add
> a test that `GET /summaries/jobs` returns the jobs list (200), not a 404 from
> the `{concept}` handler.

`docs/openapi/mintmory.yaml` — under the Summaries section add:
- `GET /summaries/jobs` (operationId `listSummaryJobs`, query `include_all`
  boolean default false, `limit` integer min 0 default 0; 200 → array of
  `SummaryJob`);
- `PUT /summaries/{concept}` (operationId `putSummary`, requestBody
  `SummaryPut`, 200 → `MemorySummary`);
- component schemas `SummaryJob` (concept, memory_ids[], contents[],
  memory_count, current_summary nullable) and `SummaryPut` (summary_text,
  required, minLength 1). Reuse the existing `{concept}` path-parameter
  definition style.

---

## 6. Determinism / invariants the implementer MUST preserve

- **`generate_summaries` is byte-for-byte equivalent.** The existing dreaming
  summary tests pass unedited. The only diff is the extraction of §0 steps 1–6
  into `_select_summary_concepts`; the early-return, concurrency branch,
  idempotency skip, upsert, and count are unchanged.
- **No LLM / no network in `collect_summary_jobs` / `apply_summary` /
  `_select_summary_concepts` / `_active_count_for_concept`.** They MUST work with
  `provider=none` and `summarizer=None`. `collect_summary_jobs` does not read
  `self.summarizer`.
- **Selection parity.** `collect_summary_jobs(include_all=True)` returns exactly
  the concepts (and the same truncated/capped `contents`) that
  `generate_summaries` would summarise for the same DB + settings.
- **Incremental rule.** Default `collect_summary_jobs` returns a concept iff it
  has no current summary OR its stored `memory_count` != current active count.
  After `apply_summary(c, ...)`, default `collect_summary_jobs()` MUST NOT return
  `c` on an unchanged DB.
- **`apply_summary` is idempotent** (INSERT OR REPLACE by concept via
  `upsert_summary`); re-applying overwrites, preserving the row `id`.
- **No new `LLMProvider`, no schema/storage migration.** `memory_summaries`,
  `MemorySummary`, `upsert_summary`/`get_summary`/`list_summaries` reused as-is.
- **Transports build the engine via `build_dreaming_engine`** (not bare
  `DreamingEngine`), so the new path uses the configured `MINTMORY_SUMMARY_*` /
  stoplist policy. `limit` is applied AFTER selection (post-cap slice), `0` = no
  cap.
- **Existing summary read paths unchanged:** `summary_list`/`GET /summaries`,
  `summary_get`/`GET /summaries/{concept}`, MCP `summary_list`/`summary_get`.

---

## 7. Tests (contract)

Group by ownership (see tasks.md). Minimum coverage:

- **core — selection-helper equivalence (`tests/test_dreaming.py`):**
  - the five existing summary tests stay green WITHOUT EDITS (the proof of
    byte-for-byte equivalence). Do NOT modify them.
  - `_select_summary_concepts` returns concepts in sorted order; `memory_count`
    matches the inline-old value (e.g. for the `aaa`×5/`bbb`×4/`ccc`×3 fixture);
    `max_content_chars` truncation + `max_contents` cap applied to `contents` and
    `memory_ids` index-aligned; `top_k` and stoplist honoured.
- **core — `collect_summary_jobs` (`tests/test_dreaming.py`):**
  - with NO summarizer configured (`summarizer=None`) and `provider=none`, jobs
    are still returned (the whole point); `include_all=True` returns every
    qualifying concept; default returns only needy concepts;
  - a concept with a current summary whose `memory_count` matches is OMITTED by
    default but INCLUDED with `include_all=True`;
  - `current_summary` is populated from an existing summary and `None` otherwise;
  - `memory_ids`/`contents` length == min(active count, `max_contents`),
    `memory_count` == full active count;
  - below-`min_memories` and stoplisted concepts never appear.
- **core — `apply_summary` (`tests/test_dreaming.py`):**
  - persists the text verbatim with `memory_count` == current active count and
    `is_current=True`; idempotent overwrite (second call replaces, `id` stable
    via `upsert_summary`);
  - `apply_summary(c, ...)` then `collect_summary_jobs()` (default) does NOT
    return `c` (the incremental round-trip);
  - works with `provider=none` / `summarizer=None`.
- **transports:**
  - MCP (`tests/test_tools.py`): `summary_jobs` returns a list of job dicts
    (incl. `include_all`, `limit`); `summary_put` stores and the concept then
    appears via `summary_get`; both work with no LLM configured.
  - CLI (`tests/test_cli.py`, typer runner): `summary-jobs` (table + `--json` +
    `--all`/`--limit`); `summary-put concept "text"`, `--file`, and stdin;
    empty-text rejection.
  - API (`tests/test_routes.py`): `GET /summaries/jobs` 200 (not shadowed by
    `{concept}`), `include_all`/`limit` query params; `PUT /summaries/{concept}`
    200 returns the stored `MemorySummary`; the put then shows up in
    `GET /summaries/{concept}`.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`,
`mypy --strict`.
