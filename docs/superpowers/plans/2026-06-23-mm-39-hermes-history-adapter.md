# MM-39 Hermes History Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Hermes session adapter that reads `~/.hermes/sessions/session_*.json` interactive transcripts into the agent-history index, registering it as a first-class source alongside claude_code, codex, and kiro.

**Architecture:** A new `adapters/hermes.py` file implements `iter_sessions(root=None)` mirroring the existing adapter contract. It reads single-JSON-object `session_*.json` files (skipping `session_cron_*` background sessions and non-`session_` files), normalises messages to `NormalizedTurn`s, and yields `(SessionSummary, list[NormalizedTurn])`. Three small registration edits wire it into `models.AGENTS`, `ingest._ALL_SOURCES`, `ingest._load_adapter`, and `ingest._COLLECTION_FOR_AGENT`.

**Tech Stack:** Python 3.12, uv workspace, ruff (line-length 100), mypy --strict, pytest. No new dependencies.

---

## Key facts (verified from real source data)

- Real files live at `~/.hermes/sessions/session_<YYYYMMDD>_<HHMMSS>_<hash>.json` — single JSON objects (NOT JSONL).
- Skip pattern: basename starts with `session_cron_` → skip. Files starting with `request_dump_` or `.jsonl` → also skip (only parse files matching `session_*.json` that are NOT `session_cron_*`).
- Message structure: `{role: "user"|"assistant"|"tool", content: str|dict|list, [tool_calls: [...]], [tool_call_id: ...]}`
- `tools_used` can be extracted from: (a) assistant messages' `tool_calls[*].function.name`, or (b) top-level `tools[*].function.name` — use both, dedup+sorted.
- Top-level object: `{session_id, model, base_url, platform, session_start, last_updated, system_prompt, tools, message_count, messages}`.

---

## File Map

| Action | Path |
|--------|------|
| **Create** | `packages/core/src/mintmory/core/history/adapters/hermes.py` |
| **Modify** | `packages/core/src/mintmory/core/history/models.py` (line 19) |
| **Modify** | `packages/core/src/mintmory/core/history/ingest.py` (lines 49-53, 111-128, 730) |
| **Modify** | `packages/core/tests/test_history_adapters.py` (append new class) |
| **Create** | `packages/core/tests/fixtures/history/hermes/session_20240315_100000_aabbccdd.json` |
| **Create** | `packages/core/tests/fixtures/history/hermes/session_cron_test123_20240315_101000.json` |
| **Modify** | `docs/agent-history.md` (sources list, lines 3-6 and diagram) |

---

## Task 1: Create the Hermes adapter

**Files:**
- Create: `packages/core/src/mintmory/core/history/adapters/hermes.py`

- [ ] **Step 1: Write `hermes.py`**

Create `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/src/mintmory/core/history/adapters/hermes.py` with this exact content:

```python
"""
history/adapters/hermes.py — adapter for Hermes agentic sessions.

Sessions live at ~/.hermes/sessions/session_<YYYYMMDD>_<HHMMSS>_<hash>.json.
Each file is a single JSON object (not JSONL):
  {
    "session_id": str,
    "model": str,
    "base_url": str,
    "platform": str,
    "session_start": ISO8601,
    "last_updated": ISO8601,
    "system_prompt": str,
    "tools": [{"type": str, "function": {"name": str, ...}}, ...],
    "message_count": int,
    "messages": [{"role": "user"|"assistant"|"tool", "content": str|dict|list,
                  "tool_calls": [...], "tool_call_id": str, ...}, ...]
  }

Interactive-only: files whose basename begins with "session_cron_" are skipped.
Files not matching session_*.json (e.g. request_dump_*.json, *.jsonl) are also
skipped — only basenames starting with "session_" and ending with ".json" are
parsed.

Fails soft per malformed session (skips, never aborts the walk).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from mintmory.core.history.models import NormalizedTurn, SessionSummary

_DEFAULT_ROOT = "~/.hermes/sessions"

_VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "tool"})


def _content_text(content: Any) -> str:
    """Flatten message content (str | dict | list | None) to plain text.

    - str  → returned as-is
    - dict or list → json.dumps with sort_keys=True for determinism
    - None or other → empty string
    """
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, sort_keys=True, ensure_ascii=False)
    return ""


def _extract_tool_name(msg: dict[str, Any]) -> str | None:
    """Best-effort extraction of a tool name from an assistant or tool message.

    For assistant messages, checks tool_calls[0].function.name.
    For tool messages, checks the content dict's 'name'/'tool' key.
    Returns None if no name can be determined.
    """
    role = msg.get("role", "")
    if role == "assistant":
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            first = tool_calls[0]
            if isinstance(first, dict):
                fn = first.get("function", {})
                if isinstance(fn, dict) and fn.get("name"):
                    return str(fn["name"])
    content = msg.get("content")
    if isinstance(content, dict):
        for key in ("name", "tool"):
            if content.get(key):
                return str(content[key])
    return None


def _parse_session(
    path: str,
) -> tuple[SessionSummary, list[NormalizedTurn]] | None:
    """Parse one Hermes session_*.json file.

    Returns (SessionSummary, turns) or None if:
      - file is not readable or contains invalid JSON
      - top-level value is not a dict
      - messages list is absent or empty
      - no usable turns after flattening
    Never raises — always fails soft.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(obj, dict):
        return None

    raw_messages = obj.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        return None

    # --- Build turns ---
    turns: list[NormalizedTurn] = []
    tools_seen: list[str] = []

    for i, msg in enumerate(raw_messages):
        if not isinstance(msg, dict):
            continue

        raw_role = msg.get("role", "")
        role = raw_role if raw_role in _VALID_ROLES else "tool"

        content = msg.get("content")
        text = _content_text(content).strip()
        if not text:
            continue

        tool_name = _extract_tool_name(msg)
        if tool_name and tool_name not in tools_seen:
            tools_seen.append(tool_name)

        turns.append(
            NormalizedTurn(
                seq=len(turns),
                ts=None,  # Hermes messages carry no per-turn timestamp
                role=role,
                text=text,
                tool_name=tool_name,
            )
        )

    if not turns:
        return None

    # --- tools_used: merge per-message tool names with top-level tools list ---
    top_tools = obj.get("tools")
    if isinstance(top_tools, list):
        for t in top_tools:
            if isinstance(t, dict):
                fn = t.get("function", {})
                if isinstance(fn, dict):
                    name = fn.get("name", "")
                    if name and name not in tools_seen:
                        tools_seen.append(name)
    tools_used = sorted(set(tools_seen))

    # --- Session metadata ---
    session_id = obj.get("session_id") or os.path.splitext(os.path.basename(path))[0]
    ts_start = obj.get("session_start") or "1970-01-01T00:00:00Z"
    ts_end = obj.get("last_updated") or ts_start

    summary = SessionSummary(
        session_id=str(session_id),
        agent="hermes",
        repo="hermes",
        repo_path="",
        branch="",
        ts_start=str(ts_start),
        ts_end=str(ts_end),
        turn_count=len(turns),
        tools_used=tools_used,
        source_path=os.path.abspath(path),
        source_offset=0,
        model=str(obj.get("model", "")),
    )
    return summary, turns


def iter_sessions(
    root: str | None = None,
) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """Iterate over interactive Hermes sessions under *root*.

    root defaults to ~/.hermes/sessions.
    Reads session_*.json files; skips session_cron_* (background routines).
    Fails soft per malformed session (skips, never aborts the walk).
    """
    if root is None:
        root = _DEFAULT_ROOT
    root_expanded = os.path.expanduser(root)

    if not os.path.isdir(root_expanded):
        return

    try:
        entries = list(os.scandir(root_expanded))
    except OSError:
        return

    for entry in entries:
        name = entry.name
        # Only parse session_*.json files (not request_dump_*, not *.jsonl)
        if not name.startswith("session_") or not name.endswith(".json"):
            continue
        # Exclude background cron sessions
        if name.startswith("session_cron_"):
            continue
        try:
            result = _parse_session(entry.path)
        except Exception:  # noqa: BLE001 — fail soft
            continue
        if result is not None:
            yield result
```

- [ ] **Step 2: Verify file was written correctly**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
python3 -c "from mintmory.core.history.adapters import hermes; print('OK')"
```

Expected: prints `OK` (no import errors). If it fails, check the file was written.

---

## Task 2: Register Hermes in models.py

**Files:**
- Modify: `packages/core/src/mintmory/core/history/models.py` (line 19)

- [ ] **Step 1: Add "hermes" to AGENTS tuple**

In `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/src/mintmory/core/history/models.py`, change line 19:

```python
# BEFORE:
AGENTS: tuple[str, ...] = ("claude_code", "codex", "kiro")

# AFTER:
AGENTS: tuple[str, ...] = ("claude_code", "codex", "kiro", "hermes")
```

- [ ] **Step 2: Verify**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
python3 -c "from mintmory.core.history.models import AGENTS; assert 'hermes' in AGENTS; print('AGENTS OK:', AGENTS)"
```

Expected: `AGENTS OK: ('claude_code', 'codex', 'kiro', 'hermes')`

---

## Task 3: Register Hermes in ingest.py (three edits)

**Files:**
- Modify: `packages/core/src/mintmory/core/history/ingest.py` (lines 49-53, 111-128, 730)

- [ ] **Step 1: Add `_COLLECTION_FOR_AGENT["hermes"]`**

In `ingest.py` around line 49-53, add `"hermes": "hermes"` to the dict:

```python
# BEFORE:
_COLLECTION_FOR_AGENT: dict[str, str] = {
    "claude_code": "claude-code",
    "codex": "codex",
    "kiro": "kiro",
}

# AFTER:
_COLLECTION_FOR_AGENT: dict[str, str] = {
    "claude_code": "claude-code",
    "codex": "codex",
    "kiro": "kiro",
    "hermes": "hermes",
}
```

- [ ] **Step 2: Add `hermes` to `_load_adapter`**

Around line 111-128, add the `elif name == "hermes"` branch before the `else`:

```python
# BEFORE:
        elif name == "kiro":
            from mintmory.core.history.adapters import kiro  # noqa: PLC0415

            _ADAPTERS[name] = kiro.iter_sessions
        else:
            raise ValueError(f"Unknown adapter: {name!r}")

# AFTER:
        elif name == "kiro":
            from mintmory.core.history.adapters import kiro  # noqa: PLC0415

            _ADAPTERS[name] = kiro.iter_sessions
        elif name == "hermes":
            from mintmory.core.history.adapters import hermes  # noqa: PLC0415

            _ADAPTERS[name] = hermes.iter_sessions
        else:
            raise ValueError(f"Unknown adapter: {name!r}")
```

- [ ] **Step 3: Add `"hermes"` to `_ALL_SOURCES`**

Around line 730:

```python
# BEFORE:
_ALL_SOURCES = ("claude_code", "codex", "kiro")

# AFTER:
_ALL_SOURCES = ("claude_code", "codex", "kiro", "hermes")
```

- [ ] **Step 4: Verify all three edits**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
python3 -c "
from mintmory.core.history.ingest import _ALL_SOURCES, _COLLECTION_FOR_AGENT, _load_adapter
assert 'hermes' in _ALL_SOURCES, '_ALL_SOURCES missing hermes'
assert _COLLECTION_FOR_AGENT.get('hermes') == 'hermes', '_COLLECTION_FOR_AGENT wrong'
fn = _load_adapter('hermes')
assert callable(fn), '_load_adapter returned non-callable'
print('All ingest registrations OK')
"
```

Expected: `All ingest registrations OK`

---

## Task 4: Create synthetic test fixtures

**Files:**
- Create: `packages/core/tests/fixtures/history/hermes/session_20240315_100000_aabbccdd.json`
- Create: `packages/core/tests/fixtures/history/hermes/session_cron_test123_20240315_101000.json`

- [ ] **Step 1: Create the hermes fixtures directory**

```bash
mkdir -p /Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/tests/fixtures/history/hermes
```

- [ ] **Step 2: Create the well-formed interactive fixture**

Create `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/tests/fixtures/history/hermes/session_20240315_100000_aabbccdd.json`:

```json
{
  "session_id": "20240315_100000_aabbccdd",
  "model": "test-model-1.0",
  "base_url": "http://localhost:11434/v1",
  "platform": "ollama",
  "session_start": "2024-03-15T10:00:00.000000",
  "last_updated": "2024-03-15T10:05:30.000000",
  "system_prompt": "You are a helpful assistant.",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "bash",
        "description": "Run a bash command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}
      }
    }
  ],
  "message_count": 5,
  "messages": [
    {
      "role": "user",
      "content": "What files are in the current directory?"
    },
    {
      "role": "assistant",
      "content": "",
      "tool_calls": [
        {
          "id": "call_001",
          "call_id": "call_001",
          "response_item_id": "resp_001",
          "type": "function",
          "function": {"name": "bash", "arguments": "{\"command\": \"ls -la\"}"}
        }
      ]
    },
    {
      "role": "tool",
      "content": "{\"output\": \"total 8\\ndrwxr-xr-x 2 user user 4096 Mar 15 10:00 .\\n\", \"exit_code\": 0}",
      "tool_call_id": "call_001"
    },
    {
      "role": "assistant",
      "content": "The directory contains the listed files."
    },
    {
      "role": "user",
      "content": {"key": "structured content example", "value": 42}
    }
  ]
}
```

- [ ] **Step 3: Create the cron fixture (must be skipped)**

Create `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/tests/fixtures/history/hermes/session_cron_test123_20240315_101000.json`:

```json
{
  "session_id": "cron_test123_20240315",
  "model": "test-model-1.0",
  "base_url": "http://localhost:11434/v1",
  "platform": "ollama",
  "session_start": "2024-03-15T10:10:00.000000",
  "last_updated": "2024-03-15T10:10:30.000000",
  "system_prompt": "Automated cron task.",
  "tools": [],
  "message_count": 2,
  "messages": [
    {"role": "user", "content": "Run scheduled task."},
    {"role": "assistant", "content": "Task complete."}
  ]
}
```

- [ ] **Step 4: Verify fixtures are valid JSON**

```bash
python3 -c "
import json
for f in [
    'packages/core/tests/fixtures/history/hermes/session_20240315_100000_aabbccdd.json',
    'packages/core/tests/fixtures/history/hermes/session_cron_test123_20240315_101000.json',
]:
    with open('/Users/alexandruiacobescu/gooseProjects/MintMory/' + f) as fh:
        data = json.load(fh)
    print('OK:', f, '| messages:', len(data.get('messages', [])))
"
```

Expected: both files print `OK` with message counts.

---

## Task 5: Write tests for the Hermes adapter

**Files:**
- Modify: `packages/core/tests/test_history_adapters.py` (append new class at the end)

- [ ] **Step 1: Append the TestHermesAdapter class**

Append to `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/core/tests/test_history_adapters.py`:

```python


# ---------------------------------------------------------------------------
# Hermes adapter
# ---------------------------------------------------------------------------


class TestHermesAdapter:
    """Tests for core.history.adapters.hermes.iter_sessions."""

    @pytest.fixture()
    def hermes_root(self) -> str:
        return str(FIXTURES_DIR / "hermes")

    def test_parses_fixture(self, hermes_root: str) -> None:
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        # Only the interactive session is yielded; cron is skipped
        assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

        summary, turns = sessions[0]

        assert summary.agent == "hermes"
        assert summary.repo == "hermes"
        assert summary.repo_path == ""
        assert summary.branch == ""
        assert summary.session_id == "20240315_100000_aabbccdd"
        assert summary.model == "test-model-1.0"
        assert summary.ts_start == "2024-03-15T10:00:00.000000"
        assert summary.ts_end == "2024-03-15T10:05:30.000000"
        assert os.path.isabs(summary.source_path)
        assert summary.source_path.endswith(".json")
        # turn_count matches actual turns (empty-content assistant turn is skipped)
        assert summary.turn_count == len(turns)

    def test_cron_session_skipped(self, hermes_root: str) -> None:
        """session_cron_*.json files must not appear in results."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        for summary, _ in sessions:
            assert not summary.session_id.startswith("cron_"), (
                f"Cron session was not skipped: {summary.session_id}"
            )
        # Confirm the fixture dir has the cron file but it was excluded
        cron_files = [
            f
            for f in os.listdir(hermes_root)
            if f.startswith("session_cron_")
        ]
        assert len(cron_files) >= 1, "Cron fixture file not found in hermes fixture dir"

    def test_content_flattening_str(self, hermes_root: str) -> None:
        """str content → NormalizedTurn with non-empty text."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        _, turns = sessions[0]

        # First user message has str content
        user_turns = [t for t in turns if t.role == "user"]
        assert len(user_turns) >= 1
        # First user turn should be the plain string message
        assert "files" in user_turns[0].text.lower() or user_turns[0].text != ""

    def test_content_flattening_dict(self, hermes_root: str) -> None:
        """dict content → NormalizedTurn with json.dumps text (non-empty)."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        _, turns = sessions[0]

        # The last user message in the fixture has dict content
        user_turns = [t for t in turns if t.role == "user"]
        # At least one user turn should be from the dict-content message
        dict_turns = [t for t in user_turns if "{" in t.text]
        assert len(dict_turns) >= 1, "No dict-flattened turn found"
        import json as _json

        parsed = _json.loads(dict_turns[-1].text)
        assert isinstance(parsed, dict)

    def test_roles_present(self, hermes_root: str) -> None:
        """user, assistant, tool roles must all be present in the fixture."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        _, turns = sessions[0]

        roles = {t.role for t in turns}
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles

    def test_seq_is_monotonic(self, hermes_root: str) -> None:
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        _, turns = sessions[0]

        seqs = [t.seq for t in turns]
        assert seqs == list(range(len(turns))), f"seq not monotonic: {seqs}"

    def test_ts_is_none_for_all_turns(self, hermes_root: str) -> None:
        """Hermes messages carry no per-turn timestamp; ts must be None."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        _, turns = sessions[0]

        for turn in turns:
            assert turn.ts is None, f"Expected ts=None, got {turn.ts!r}"

    def test_tools_used_populated(self, hermes_root: str) -> None:
        """tools_used should include 'bash' (from tool_calls and top-level tools)."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        summary, _ = sessions[0]

        assert "bash" in summary.tools_used

    def test_soft_fail_malformed_json(self, tmp_path: Path) -> None:
        """Invalid JSON is skipped; other valid sessions in the same dir still yield."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        # Bad file
        bad = tmp_path / "session_bad_20240101_000000_aaaa.json"
        bad.write_text("NOT VALID JSON AT ALL", encoding="utf-8")

        # Good file
        good = tmp_path / "session_good_20240101_000001_bbbb.json"
        good.write_text(
            '{"session_id": "good001", "model": "m", "session_start": "2024-01-01T00:00:00Z",'
            ' "last_updated": "2024-01-01T00:01:00Z", "messages": ['
            '{"role": "user", "content": "hello"},'
            '{"role": "assistant", "content": "world"}'
            "]}",
            encoding="utf-8",
        )

        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        summary, turns = sessions[0]
        assert summary.session_id == "good001"
        assert len(turns) == 2

    def test_soft_fail_empty_messages(self, tmp_path: Path) -> None:
        """A session with an empty messages array is skipped."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        empty = tmp_path / "session_empty_20240101_000002_cccc.json"
        empty.write_text(
            '{"session_id": "empty001", "model": "m", "session_start": "2024-01-01T00:00:00Z",'
            ' "last_updated": "2024-01-01T00:00:01Z", "messages": []}',
            encoding="utf-8",
        )

        good = tmp_path / "session_good_20240101_000003_dddd.json"
        good.write_text(
            '{"session_id": "good002", "model": "m", "session_start": "2024-01-01T00:02:00Z",'
            ' "last_updated": "2024-01-01T00:03:00Z", "messages": ['
            '{"role": "user", "content": "hi"},'
            '{"role": "assistant", "content": "bye"}'
            "]}",
            encoding="utf-8",
        )

        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        assert sessions[0][0].session_id == "good002"

    def test_nonexistent_root_yields_nothing(self) -> None:
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root="/tmp/does_not_exist_mintmory_hermes"))
        assert sessions == []

    def test_cron_skipped_in_mixed_dir(self, tmp_path: Path) -> None:
        """session_cron_*.json in a dir with interactive sessions must not yield."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        # Good interactive session
        good = tmp_path / "session_interactive_20240101_000000_eeee.json"
        good.write_text(
            '{"session_id": "inter001", "model": "m", "session_start": "2024-01-01T00:00:00Z",'
            ' "last_updated": "2024-01-01T00:01:00Z", "messages": ['
            '{"role": "user", "content": "test"},'
            '{"role": "assistant", "content": "done"}'
            "]}",
            encoding="utf-8",
        )

        # Cron session alongside it
        cron = tmp_path / "session_cron_abc123_20240101_000100.json"
        cron.write_text(
            '{"session_id": "cron001", "model": "m", "session_start": "2024-01-01T00:01:00Z",'
            ' "last_updated": "2024-01-01T00:02:00Z", "messages": ['
            '{"role": "user", "content": "scheduled"},'
            '{"role": "assistant", "content": "done"}'
            "]}",
            encoding="utf-8",
        )

        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        assert sessions[0][0].session_id == "inter001"

    def test_filename_stem_used_when_session_id_absent(self, tmp_path: Path) -> None:
        """If session_id field is absent, the filename stem is used."""
        from mintmory.core.history.adapters.hermes import iter_sessions

        f = tmp_path / "session_nosid_20240101_000000_ffff.json"
        f.write_text(
            '{"model": "m", "session_start": "2024-01-01T00:00:00Z",'
            ' "last_updated": "2024-01-01T00:00:01Z", "messages": ['
            '{"role": "user", "content": "hi"},'
            '{"role": "assistant", "content": "bye"}'
            "]}",
            encoding="utf-8",
        )

        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        assert sessions[0][0].session_id == "session_nosid_20240101_000000_ffff"

    def test_turn_count_matches_turns(self, hermes_root: str) -> None:
        from mintmory.core.history.adapters.hermes import iter_sessions

        sessions = list(iter_sessions(root=hermes_root))
        summary, turns = sessions[0]
        assert summary.turn_count == len(turns)


# ---------------------------------------------------------------------------
# Registry wiring tests
# ---------------------------------------------------------------------------


class TestHermesRegistry:
    """Tests that Hermes is correctly wired into the global registry."""

    def test_hermes_in_all_sources(self) -> None:
        from mintmory.core.history.ingest import _ALL_SOURCES

        assert "hermes" in _ALL_SOURCES

    def test_hermes_in_agents(self) -> None:
        from mintmory.core.history.models import AGENTS

        assert "hermes" in AGENTS

    def test_collection_slug(self) -> None:
        from mintmory.core.history.ingest import _COLLECTION_FOR_AGENT

        assert _COLLECTION_FOR_AGENT.get("hermes") == "hermes"

    def test_load_adapter_returns_callable(self) -> None:
        from mintmory.core.history.ingest import _load_adapter

        fn = _load_adapter("hermes")
        assert callable(fn)

    def test_load_adapter_returns_iter_sessions(self) -> None:
        from mintmory.core.history.adapters.hermes import iter_sessions
        from mintmory.core.history.ingest import _load_adapter

        fn = _load_adapter("hermes")
        assert fn is iter_sessions
```

- [ ] **Step 2: Run only the new Hermes tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/core/tests/test_history_adapters.py::TestHermesAdapter packages/core/tests/test_history_adapters.py::TestHermesRegistry -v
```

Expected: all tests pass. If a test fails, diagnose:
- `test_parses_fixture` failing? → Check fixture JSON matches what the adapter expects.
- `test_content_flattening_dict` failing? → The dict-content user message may not be turning into a turn (check the last user message has non-empty text after json.dumps).
- `test_tools_used_populated` failing? → The assistant tool_call extraction may not be reading `tool_calls[0].function.name`.

---

## Task 6: Update docs/agent-history.md

**Files:**
- Modify: `docs/agent-history.md`

- [ ] **Step 1: Update intro paragraph and diagram**

In `/Users/alexandruiacobescu/gooseProjects/MintMory/docs/agent-history.md`:

Change line 3:
```markdown
# BEFORE (line 3):
MintMory can index the chat history of your coding agents — **Claude Code,
Codex, and Kiro** — into one searchable, time-aware changelog, ...

# AFTER:
MintMory can index the chat history of your coding agents — **Claude Code,
Codex, Kiro, and Hermes** — into one searchable, time-aware changelog, ...
```

Change the diagram (lines 24-26):
```
# BEFORE:
~/.claude/projects/**.jsonl ─┐
~/.codex/sessions/**.jsonl  ─┤  adapters → redact secrets → distill →  ~/.mintmory/
Kiro globalStorage sessions ─┘  (one dated summary per session)         agent-history.db

# AFTER:
~/.claude/projects/**.jsonl   ─┐
~/.codex/sessions/**.jsonl    ─┤  adapters → redact secrets → distill →  ~/.mintmory/
Kiro globalStorage sessions   ─┤  (one dated summary per session)         agent-history.db
~/.hermes/sessions/session_*  ─┘
```

Change line 37:
```markdown
# BEFORE:
  `source=AGENT`, and `collection ∈ {claude-code, codex, kiro}`, and lives in a

# AFTER:
  `source=AGENT`, and `collection ∈ {claude-code, codex, kiro, hermes}`, and lives in a
```

Change line 71 (CLI table row for backfill):
```markdown
# BEFORE:
| `mintmory history backfill [--source claude_code\|codex\|kiro] [--limit N] [--db PATH]` | ...

# AFTER:
| `mintmory history backfill [--source claude_code\|codex\|kiro\|hermes] [--limit N] [--db PATH]` | ...
```

Change line 72 (CLI table row for sync):
```markdown
# BEFORE:
| `mintmory history sync [--source …] [--db PATH]` | ...

# AFTER (no change needed — `--source …` already covers it)
```

Change line 120 (--source example):
```markdown
# BEFORE:
- **"Index only one tool"** → `mintmory history backfill --source codex`

# AFTER:
- **"Index only one tool"** → `mintmory history backfill --source codex` (or `--source hermes` for Hermes sessions)
```

- [ ] **Step 2: Verify doc changes**

```bash
grep -n "hermes\|Hermes" /Users/alexandruiacobescu/gooseProjects/MintMory/docs/agent-history.md
```

Expected: at least 3-4 lines containing Hermes references.

---

## Task 7: Run all quality gates

- [ ] **Step 1: ruff lint**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check .
```

Expected: no errors. If any in `hermes.py`, fix them (common: `BLE001` already suppressed, line length issues).

- [ ] **Step 2: ruff format**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff format packages
```

Expected: `N files reformatted` or `N files left unchanged`.

- [ ] **Step 3: mypy strict**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync mypy packages
```

Expected: `Success: no issues found`. Common mypy fixes needed:
- If `Any` from `typing` causes issues → already imported via `from typing import Any`.
- If `json.dumps` return type issues → `str` which is fine.
- If `obj.get(...)` return type is `Any` → that's correct since JSON dicts have `Any` values.

- [ ] **Step 4: Full test suite**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q
```

Expected: ≥80% pass rate; all existing tests green; new Hermes tests green.

- [ ] **Step 5: openspec validate**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
openspec validate add-hermes-history-adapter --strict
```

Expected: `✓ validated` or similar success output.

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task |
|-------------|------|
| `adapters/hermes.py` with `iter_sessions(root=None)` | Task 1 |
| Skip `session_cron_*` | Task 1, `iter_sessions` filter |
| `_parse_session` soft-fail on error/empty | Task 1, `_parse_session` |
| `_content_text` for str/dict/list | Task 1, `_content_text()` |
| `tools_used` dedup+sorted from tool_calls + top-level | Task 1, `_parse_session` |
| `session_id` fallback to filename stem | Task 1, `_parse_session` |
| `ts_start`/`ts_end` from session_start/last_updated | Task 1, `_parse_session` |
| Fallback ts to `"1970-01-01T00:00:00Z"` | Task 1, `_parse_session` |
| `agent="hermes"`, `repo="hermes"`, `repo_path=""`, `branch=""` | Task 1 |
| `models.AGENTS` += `"hermes"` | Task 2 |
| `ingest._ALL_SOURCES` += `"hermes"` | Task 3 |
| `ingest._load_adapter` += hermes branch | Task 3 |
| `ingest._COLLECTION_FOR_AGENT["hermes"] = "hermes"` | Task 3 |
| Fixture: well-formed interactive session | Task 4 |
| Fixture: cron session (proves exclusion) | Task 4 |
| Test: parses fixture correctly | Task 5 |
| Test: content flattening (str + dict) | Task 5 |
| Test: cron skipped | Task 5 |
| Test: malformed JSON soft-skipped | Task 5 |
| Test: empty messages soft-skipped | Task 5 |
| Test: registry wiring | Task 5, `TestHermesRegistry` |
| Docs: Hermes in sources list | Task 6 |
| Gate: ruff + mypy + pytest + openspec | Task 7 |

### No real session data committed

The fixtures in `packages/core/tests/fixtures/history/hermes/` are fully synthetic — generated content with no relation to actual user sessions from `~/.hermes/sessions/`.
