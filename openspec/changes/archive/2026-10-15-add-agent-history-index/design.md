# Design & FROZEN interface contract — `add-agent-history-index`

Implementers MUST match these names, signatures, defaults, and behaviours exactly.
Where intuition and this doc disagree, this doc wins. Everything is **additive**;
no existing module/schema/behaviour changes. v1 is **deterministic (no LLM)**.

New subpackage: `packages/core/src/mintmory/core/history/`
```
history/__init__.py
history/models.py        # schema (dataclasses)
history/redact.py        # secret redaction (hard gate)
history/normalize.py     # sessionizer helpers (repo/branch/time)
history/distill.py       # deterministic summary (LLM seam)
history/adapters/__init__.py
history/adapters/claude_code.py
history/adapters/codex.py
history/adapters/kiro.py
history/ingest.py        # writer + backfill/sync + manifest + hermes-guard
```

---

## 1. `models.py` — normalized schema (stdlib dataclasses, frozen)

```python
from dataclasses import dataclass, field

AGENTS = ("claude_code", "codex", "kiro")
KINDS = ("fix", "feature", "refactor", "investigation", "chore", "docs", "incident")

@dataclass
class NormalizedTurn:
    seq: int
    ts: str | None            # ISO-8601 UTC, or None
    role: str                 # "user" | "assistant" | "tool"
    text: str
    tool_name: str | None = None

@dataclass
class SessionSummary:
    session_id: str
    agent: str                # one of AGENTS
    repo: str                 # git-root basename, else cwd basename, else "unknown"
    repo_path: str            # absolute cwd/workspace path ("" if unknown)
    branch: str               # "" if unknown
    ts_start: str             # ISO-8601 UTC (session's first turn / meta time)
    ts_end: str               # ISO-8601 UTC (last turn time; == ts_start if 1)
    turn_count: int
    tools_used: list[str] = field(default_factory=list)
    kind: str = "investigation"   # one of KINDS
    title: str = ""
    summary_text: str = ""        # changelog voice, <= 600 chars
    source_path: str = ""         # absolute path to the session file
    source_offset: int = 0        # byte offset of the session start (0 for whole-file)
    model: str = ""               # model id if known
    distiller_version: int = 1
```

A source adapter yields `tuple[SessionSummary, list[NormalizedTurn]]` per session
(summary fields `kind/title/summary_text` left at defaults — the distiller fills them).

---

## 2. `redact.py` — secret redaction (HARD GATE)

```python
import re
_PATTERNS: list[tuple[str, re.Pattern[str]]]   # (placeholder_label, compiled)

def redact(text: str) -> str:
    """Replace every secret match with '[REDACTED:<label>]'. Over-redact by design."""
```
MUST cover at least: OpenAI-style `sk-`/`pk-`/`rk-` keys; `mk_agent_[A-Za-z0-9]{20,}`;
JWTs `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`; `AKIA[0-9A-Z]{16}`;
GitHub `gh[pousr]_[A-Za-z0-9]{20,}`; PEM `-----BEGIN [A-Z ]*PRIVATE KEY-----...END...`;
`Authorization:` header values (keep header name, redact value). Idempotent (running
twice changes nothing). `redact()` is called by the writer on EVERY persisted string
(title/summary_text) and by the distiller on its input — there is no path that
persists or LLM-sends un-redacted text.

```python
def scan(text: str) -> dict[str, int]:
    """Return {label: count} of secret patterns found (for the `scrub` audit). No mutation."""
```

---

## 3. `normalize.py` — helpers

```python
def to_utc_iso(ts: str | int | float | None) -> str | None:
    """Coerce epoch seconds/ms or an ISO string to ISO-8601 UTC 'Z'; None -> None."""

def resolve_repo(cwd: str | None) -> tuple[str, str]:
    """Return (repo_name, repo_path). Walk up cwd to a '.git' dir (handle worktrees:
    a '.git' FILE pointing at the real gitdir -> use the main worktree path); repo_name
    = basename of the git root; fallback (repo_name=basename(cwd) or 'unknown',
    repo_path=cwd or '')."""
```

---

## 4. `distill.py` — deterministic distiller (LLM seam)

```python
def distill(summary: SessionSummary, turns: list[NormalizedTurn]) -> SessionSummary:
    """Fill title/kind/summary_text deterministically (NO network, NO LLM) and return
    a NEW SessionSummary (dataclasses.replace). Rules:
      - title: first non-empty user turn, first line, trimmed to <= 80 chars.
      - summary_text (<= 600 chars, changelog voice): combine the first user turn
        (the ask) + the last assistant turn (the outcome) + a tools/files hint
        ('touched N files; tools: edit, bash'); collapse whitespace.
      - kind: keyword heuristic over title+summary (fix|bug|error->fix;
        add|implement|feature->feature; refactor/rename->refactor; doc->docs;
        else investigation). Deterministic + idempotent.
    Both inputs are already redacted upstream; distill MUST NOT undo redaction."""
```
A future `distill_llm(summary, turns, client)` is an explicit seam; v1 wires only
`distill`. `distiller_version` stays 1.

---

## 5. `adapters/*.py` — one function each

Each adapter is a generator over sessions for its source root. Adapters read the
real files (they MAY introspect payload shapes) but MUST emit the frozen schema.
Adapters MUST fail soft per-file (skip a malformed session, never abort the walk).

```python
# claude_code.py
def iter_sessions(root: str | None = None) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """root defaults to ~/.claude/projects. One <uuid>.jsonl = one session. Lines:
    {type, message, timestamp, cwd, gitBranch, sessionId, isSidechain, ...}.
    type user/assistant -> roles; message.content is str OR a list of blocks
    (text / tool_use / tool_result) -> flatten to text, tool turns get role='tool'
    + tool_name. Skip isSidechain lines. repo from resolve_repo(cwd); ts from
    timestamp; source_path = file, source_offset = 0."""

# codex.py
def iter_sessions(root: str | None = None) -> Iterator[...]:
    """root defaults to ~/.codex/sessions. rollout-*.jsonl lines {type,timestamp,payload}:
    type session_meta (payload has id, cwd, model/provider), response_item (payload
    role+content[input_text/output_text]), event_msg (skip or tool). Enrich title from
    ~/.codex/session_index.jsonl (id->thread_name) when present. Honor
    ~/.codex/external_agent_session_imports.json: skip ids listed as imported-from-foreign
    to avoid double counting. Skip ~/.codex/sqlite / codex-dev.db."""

# kiro.py
def iter_sessions(root: str | None = None) -> Iterator[...]:
    """root defaults to ~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent.
    Sessions live under workspace-sessions/<b64url(workspace_path)>/<uuid>.json with a
    sibling sessions.json (list mapping sessionId->dateCreated/title). Decode the dir
    name (urlsafe_b64decode, restore padding) -> workspace_path -> resolve_repo.
    Session json has history[] of {role/sender, content/text}. Ignore *.vscdb."""
```

---

## 6. `ingest.py` — writer, backfill/sync, guard

```python
DEFAULT_HISTORY_DB = "~/.mintmory/agent-history.db"   # expanduser at call time

class HermesGuardError(RuntimeError): ...

def _assert_not_working_db(db_path: str) -> None:
    """Raise HermesGuardError if db_path resolves to the working store: the
    MINTMORY_DB env value, the CLI default (~/.mintmory/memories.db), or any
    '*/hermes.db'. The history DB MUST be a distinct file."""

_ADAPTERS = {"claude_code": ..., "codex": ..., "kiro": ...}  # name -> iter_sessions

def write_session(adapter_db: StorageAdapter, summary: SessionSummary) -> str | None:
    """Redact title+summary_text; build a MemoryRecord(content=summary_text or title,
    category=EPISODIC, source=AGENT, valid_from=ts_start, metadata=envelope) where
    envelope = {record_type:'session_summary', agent, repo, repo_path, branch, kind,
    session_id, ts_start, ts_end, turn_count, tools_used, source_path, source_offset,
    model, distiller_version}. Idempotent on session_id: if a memory with
    metadata.session_id exists, update_memory; else add_memory. Returns memory id (or
    None if summary_text empty)."""

def backfill(db_path: str = DEFAULT_HISTORY_DB, sources: list[str] | None = None,
             *, limit: int = 0) -> "IngestReport":
    """_assert_not_working_db; open/initialise the dedicated StorageAdapter; for each
    source adapter, iter_sessions -> distill -> write_session; record per-file
    index_manifest rows (collection=source, path+content_hash+mtime) to skip
    unchanged files on re-run. limit>0 caps sessions per source (for smoke)."""

def sync(db_path: str = DEFAULT_HISTORY_DB, sources: list[str] | None = None) -> "IngestReport":
    """Like backfill but skips sessions whose source file is unchanged per
    index_manifest (size+mtime+content_hash); only (re)distills changed/new files."""

@dataclass
class IngestReport:
    scanned: int; written: int; updated: int; skipped: int; redacted_hits: int
    by_source: dict[str, int]
```
The dedicated DB is created with `chmod 0o600`. `EPISODIC` and `AGENT` are existing
enum members (verify in `types.py`); use them (no schema/enum change).

---

## 7. CLI — `mintmory history` group (`packages/cli`)

Add a Typer sub-app `history` with:
- `mintmory history backfill [--source claude_code|codex|kiro ...] [--db PATH] [--limit N]`
- `mintmory history sync [--source ...] [--db PATH]`
- `mintmory history timeline [--since 60d|--from ISO --to ISO] [--repo R] [--kind K] [--limit N]`
  — query the history DB on `valid_from` within the window (parse `--since` like `75d`/`8w`/`3m`),
  filter metadata repo/kind, sort `valid_from` desc, print a dated changelog table.
- `mintmory history search QUERY [--repo R] [--since ...] [--limit N]` — hybrid search
  over the history DB (record_type=session_summary), newest-first within matches.
- `mintmory history scrub [--db PATH]` — run `redact.scan` over stored summaries;
  report any residual secret counts (exit non-zero if any found).

All commands default `--db` to `DEFAULT_HISTORY_DB` and call `_assert_not_working_db`.

---

## 8. Tests (contract)
- `test_history_redact.py`: each pattern redacts; idempotent; `scan` counts; a real
  `mk_agent_`/JWT/`sk-` sample is fully scrubbed.
- `test_history_models_distill.py`: deterministic distill is pure + idempotent; kind
  heuristic; 600/80-char caps; never un-redacts.
- `test_history_adapters.py`: each adapter parses a small committed fixture
  (one tiny Claude jsonl, one Codex rollout, one Kiro session+sessions.json under
  `packages/core/tests/fixtures/history/`) into the frozen schema; fail-soft on a
  malformed line.
- `test_history_ingest.py`: `_assert_not_working_db` raises for hermes.db / MINTMORY_DB
  / memories.db; backfill into a temp DB writes EPISODIC+AGENT+envelope; re-run skips
  (manifest dedup); session_id re-distill updates not duplicates; valid_from == ts_start.
- `test_history_cli.py`: `timeline --since` window filters by valid_from; `scrub` flags
  a planted secret.

All gates: `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
Do NOT point any test at the real `~/.claude` / `~/.codex` / `~/.mintmory` — tests use
temp dirs + fixtures only.
