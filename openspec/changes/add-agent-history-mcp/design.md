# Design & FROZEN interface contract — `add-agent-history-mcp`

Match these names/signatures/behaviours exactly. Additive; the existing
`mintmory-mcp` server and `mintmory history` CLI behaviour are unchanged.

---

## 1. `core/history/query.py` — shared read-only query module (NEW)

```python
from datetime import datetime, timedelta

DEFAULT_WINDOW_DAYS = 90

def resolve_window(
    *, since: str | None, from_iso: str | None, to_iso: str | None, now: datetime
) -> tuple[datetime, datetime]:
    """Return (start, end) naive-UTC datetimes.
    - since ('75d'/'8w'/'3m'/'2y') is mutually exclusive with from/to -> ValueError if both.
    - since -> (now - delta, now); from/to -> (parse(from) or datetime.min, parse(to) or now);
    - neither -> (now - DEFAULT_WINDOW_DAYS, now).
    Reuse the CLI's existing since-grammar (d/w/m/y -> days*1/7/30/365)."""

def _open_history(db_path: str) -> StorageAdapter:
    """expanduser(db_path); _assert_not_working_db(...) (HermesGuardError); open + return.
    Read-only intent: callers never write."""

def timeline(
    db_path: str,
    *,
    since: str | None = None,
    from_iso: str | None = None,
    to_iso: str | None = None,
    repo: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Session summaries with valid_from in the window, newest-first.
    Query: is_archived=0 AND metadata.record_type='session_summary'
      AND valid_from in [start,end] (+ optional metadata.repo / metadata.kind),
      ORDER BY valid_from DESC LIMIT ?.
    Each row dict: {date (YYYY-MM-DD), ts_start, agent, collection, repo, branch,
      kind, title, summary (=content), session_id, source_path}."""

def search(
    db_path: str,
    query: str,
    *,
    repo: str | None = None,
    since: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Hybrid search (StorageAdapter.search) over record_type='session_summary',
    optionally constrained to repo and to valid_from >= (now - since). Return the
    same row dict shape as timeline(), in search-rank order. Use a MemoryFilter or
    post-filter on metadata.record_type so only session summaries are returned."""
```
`now` param defaults to `datetime.now(UTC).replace(tzinfo=None)` when None (keeps
tests deterministic). All times naive-UTC to match storage `valid_from`.

The CLI `history timeline` / `history search` (in `packages/cli`) MUST be
refactored to call `query.timeline` / `query.search` and only render the returned
rows — no behaviour change to the CLI output/flags.

---

## 2. `packages/mcp/src/mintmory/mcp/history_server.py` — read-only MCP (NEW)

A FastMCP server, structured like `server.py` but with ONLY read tools.

```python
mcp: FastMCP[Any] = FastMCP("mintmory-history", instructions=<short policy>)

def _db_path() -> str:
    return os.environ.get("MINTMORY_HISTORY_DB", os.path.expanduser(DEFAULT_HISTORY_DB))
```

Tools (exactly these three; NO write tools):
```python
@mcp.tool()
def history_timeline(since: str = "90d", from_date: str | None = None,
                     to_date: str | None = None, repo: str | None = None,
                     kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Dated changelog of agent sessions in a time window (the 'what changed N ago'
    query). Returns newest-first session summaries."""
    return query.timeline(_db_path(), since=since, from_iso=from_date, to_iso=to_date,
                          repo=repo, kind=kind, limit=limit)

@mcp.tool()
def history_search(query_text: str, repo: str | None = None,
                   since: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Hybrid search across indexed agent session summaries."""
    return query.search(_db_path(), query_text, repo=repo, since=since, limit=limit)

@mcp.tool()
def history_stats() -> dict[str, Any]:
    """Counts of indexed sessions by source (collection) and kind, plus the
    earliest/latest session dates. Read-only."""
```
`instructions` should tell the agent: this server is READ-ONLY history of past
coding sessions across Claude Code / Codex / Kiro; use `history_timeline` for
"what changed/was fixed in the last N days/weeks/months", `history_search` for
topic recall; results are dated session summaries with `source_path` back-links.

```python
def main() -> None:
    # argparse: --transport {stdio,sse} (default stdio), --port (default 8082),
    # --db (sets MINTMORY_HISTORY_DB). On startup call _assert_not_working_db(_db_path())
    # so a misconfigured DB fails fast. Then mcp.run(transport=...).
```
The guard MUST run before serving. No tool may write, archive, add, or dream.

---

## 3. Entry point — `packages/mcp/pyproject.toml`

Add under `[project.scripts]`:
```
mintmory-history-mcp = "mintmory.mcp.history_server:main"
```

---

## 4. Tests (contract)
- `packages/core/tests/test_history_query.py`: `resolve_window` (since vs from/to
  mutual-exclusion raises; d/w/m/y grammar; default 90d); `timeline` filters by
  window + repo + kind, newest-first, correct row keys; `search` returns only
  session summaries; both raise `HermesGuardError` for hermes.db/memories.db.
  (Build a temp history DB via `history.ingest.write_session` with known dates.)
- `packages/mcp/tests/test_history_mcp.py`: the server registers exactly
  `history_timeline`, `history_search`, `history_stats` and **no** write tools
  (assert none of memory_add/memory_dream/memory_archive/summary_put/etc. exist on
  it); `history_timeline` returns rows from a temp DB (set MINTMORY_HISTORY_DB);
  `main()`-level guard refuses a working-store path.

All gates: `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
Tests use temp DBs only — never the real `~/.mintmory/agent-history.db`.
