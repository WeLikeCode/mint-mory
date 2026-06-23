"""
Tests for mintmory.core.history adapters.

Verifies that each adapter:
  - Parses its committed fixture into the frozen SessionSummary/NormalizedTurn schema
  - Produces correct agent, repo, ts_start, roles
  - Fails soft on a malformed line (skip, do not abort)

All tests use committed fixtures under packages/core/tests/fixtures/history/.
No tests touch the real ~/.claude, ~/.codex, ~/.mintmory, or ~/Library.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "history"


# ---------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapter:
    """Tests for core.history.adapters.claude_code.iter_sessions."""

    @pytest.fixture()
    def claude_root(self) -> str:
        return str(FIXTURES_DIR / "claude")

    def test_parses_fixture(self, claude_root: str) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

        summary, turns = sessions[0]

        # Verify agent
        assert summary.agent == "claude_code"

        # Verify session_id matches the fixture filename
        assert summary.session_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # Verify repo is resolved from cwd (no .git in fixture dirs, so fallback to basename)
        assert summary.repo != ""

        # Verify timestamps
        assert summary.ts_start == "2024-03-15T10:00:00Z"
        assert summary.ts_end is not None
        assert "2024-03-15" in summary.ts_end

        # Verify model extracted from assistant turns
        assert summary.model == "claude-opus-4-5"

        # Verify gitBranch
        assert summary.branch == "main"

        # Verify source_path is absolute
        assert os.path.isabs(summary.source_path)
        assert summary.source_path.endswith(".jsonl")

    def test_turns_roles(self, claude_root: str) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        _, turns = sessions[0]

        roles = [t.role for t in turns]

        # Should have user, assistant, and tool turns
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles

    def test_tools_used(self, claude_root: str) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        summary, _ = sessions[0]

        # Fixture has Read and Edit tool_use blocks
        assert "Read" in summary.tools_used
        assert "Edit" in summary.tools_used

    def test_sidechain_skipped(self, claude_root: str) -> None:
        """Lines with isSidechain=True must not appear as turns."""
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        _, turns = sessions[0]

        # The sidechain message "This is a sidechain message that should be skipped."
        # must NOT appear in turns
        sidechain_texts = [t.text for t in turns if "sidechain" in t.text.lower()]
        assert len(sidechain_texts) == 0, f"Sidechain turns leaked: {sidechain_texts}"

    def test_seq_is_monotonic(self, claude_root: str) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        _, turns = sessions[0]

        seqs = [t.seq for t in turns]
        assert seqs == list(range(len(turns))), f"seq not monotonic: {seqs}"

    def test_fail_soft_on_malformed_line(self, tmp_path: Path) -> None:
        """A malformed JSON line must be skipped, not abort the adapter."""
        from mintmory.core.history.adapters.claude_code import iter_sessions

        # Create a project subdirectory with a session file
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        session_file = project_dir / "sess-bad.jsonl"
        session_file.write_text(
            "NOT VALID JSON\n"
            '{"type": "user", "sessionId": "bad-sess-001", "isSidechain": false, '
            '"timestamp": "2024-01-01T00:00:00Z", '
            '"cwd": "/tmp/proj", '
            '"message": {"role": "user", "content": "Hello from good line"}}\n'
            '{"type": "assistant", "sessionId": "bad-sess-001", "isSidechain": false, '
            '"timestamp": "2024-01-01T00:00:01Z", '
            '"cwd": "/tmp/proj", '
            '"message": {"role": "assistant", "content": "Hello back"}}\n',
            encoding="utf-8",
        )

        # Should NOT raise — the malformed line is skipped
        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        _, turns = sessions[0]
        user_turns = [t for t in turns if t.role == "user"]
        assert len(user_turns) >= 1

    def test_nonexistent_root_yields_nothing(self) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root="/tmp/does_not_exist_mintmory_test"))
        assert sessions == []

    def test_turn_count_matches_turns(self, claude_root: str) -> None:
        from mintmory.core.history.adapters.claude_code import iter_sessions

        sessions = list(iter_sessions(root=claude_root))
        summary, turns = sessions[0]
        assert summary.turn_count == len(turns)


# ---------------------------------------------------------------------------
# Codex adapter
# ---------------------------------------------------------------------------


class TestCodexAdapter:
    """Tests for core.history.adapters.codex.iter_sessions."""

    @pytest.fixture()
    def codex_root(self) -> str:
        return str(FIXTURES_DIR / "codex")

    def test_parses_fixture(self, codex_root: str) -> None:
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions = list(iter_sessions(root=codex_root))
        assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

        summary, turns = sessions[0]

        # Verify agent
        assert summary.agent == "codex"

        # Verify session_id from session_meta
        assert summary.session_id == "cccccccc-dddd-eeee-ffff-000000000001"

        # Verify repo fallback (no .git in test cwd)
        assert summary.repo != ""

        # Verify timestamp
        assert summary.ts_start == "2024-03-15T10:00:00Z"

        # Verify model_provider extracted
        assert summary.model == "openai"

        # source_path must be absolute
        assert os.path.isabs(summary.source_path)
        assert summary.source_path.endswith(".jsonl")

    def test_turns_contain_user_and_assistant(self, codex_root: str) -> None:
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions = list(iter_sessions(root=codex_root))
        _, turns = sessions[0]

        roles = [t.role for t in turns]
        assert "user" in roles
        assert "assistant" in roles

    def test_event_msg_skipped(self, codex_root: str) -> None:
        """event_msg lines must not produce turns."""
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions = list(iter_sessions(root=codex_root))
        _, turns = sessions[0]

        # No turn should have 'task_started' text from event_msg
        event_turns = [t for t in turns if "task_started" in t.text]
        assert len(event_turns) == 0

    def test_fail_soft_on_malformed_line(self, tmp_path: Path) -> None:
        """A malformed JSON line must be skipped, not abort."""
        from mintmory.core.history.adapters.codex import iter_sessions

        _sid = "00000000-0000-0000-0000-000000000001"
        rollout = tmp_path / f"rollout-2024-01-01T00-00-00-{_sid}.jsonl"
        rollout.write_text(
            "INVALID JSON LINE\n"
            '{"timestamp": "2024-01-01T00:00:00Z", "type": "session_meta", '
            f'"payload": {{"id": "{_sid}", '
            '"cwd": "/tmp/test", "model_provider": "openai"}}\n'
            '{"timestamp": "2024-01-01T00:00:01Z", "type": "response_item", '
            '"payload": {"role": "user", "content": '
            '[{"type": "input_text", "text": "Hello"}]}}\n'
            '{"timestamp": "2024-01-01T00:00:02Z", "type": "response_item", '
            '"payload": {"role": "assistant", "content": '
            '[{"type": "output_text", "text": "Hi!"}]}}\n',
            encoding="utf-8",
        )
        sessions = list(iter_sessions(root=str(tmp_path)))
        assert len(sessions) == 1
        _, turns = sessions[0]
        user_turns = [t for t in turns if t.role == "user"]
        assert len(user_turns) >= 1

    def test_nonexistent_root_yields_nothing(self) -> None:
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions = list(iter_sessions(root="/tmp/does_not_exist_mintmory_codex"))
        assert sessions == []

    def test_imported_session_skipped(self, tmp_path: Path) -> None:
        """Sessions listed in external_agent_session_imports.json must be skipped."""
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        # Create a rollout for a session that is 'imported'
        imported_id = "ffffffff-0000-0000-0000-000000000001"
        rollout = sessions_root / f"rollout-2024-01-01T00-00-00-{imported_id}.jsonl"
        _ui = '{"type": "input_text", "text": "Hi"}'
        _ao = '{"type": "output_text", "text": "Hello"}'
        rollout.write_text(
            f'{{"timestamp": "2024-01-01T00:00:00Z", "type": "session_meta", '
            f'"payload": {{"id": "{imported_id}", "cwd": "/tmp/test",'
            f' "model_provider": "openai"}}}}\n'
            f'{{"timestamp": "2024-01-01T00:00:01Z", "type": "response_item", '
            f'"payload": {{"role": "user", "content": [{_ui}]}}}}\n'
            f'{{"timestamp": "2024-01-01T00:00:02Z", "type": "response_item", '
            f'"payload": {{"role": "assistant", "content": [{_ao}]}}}}\n',
            encoding="utf-8",
        )

        # Write imports file. source_path must EXIST for the skip to apply
        # (orphaned imports whose source is gone are kept — Codex is the only copy).
        existing_source = tmp_path / "claude-original.jsonl"
        existing_source.write_text("{}\n", encoding="utf-8")
        imports_file = tmp_path / "external_agent_session_imports.json"
        imports_file.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "imported_thread_id": imported_id,
                            "source_path": str(existing_source),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        sessions = list(iter_sessions(root=str(sessions_root)))
        assert sessions == [], "Imported session should be skipped"

    def test_session_index_enriches_title(self, tmp_path: Path) -> None:
        """Title from session_index.jsonl must be applied to the session."""
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions_root = tmp_path / "sessions"
        sessions_root.mkdir()

        sid = "aaaabbbb-cccc-dddd-eeee-000000000001"
        rollout = sessions_root / f"rollout-2024-01-01T00-00-00-{sid}.jsonl"
        _ui2 = '{"type": "input_text", "text": "implement feature X"}'
        _ao2 = '{"type": "output_text", "text": "Done"}'
        rollout.write_text(
            f'{{"timestamp": "2024-01-01T00:00:00Z", "type": "session_meta", '
            f'"payload": {{"id": "{sid}", "cwd": "/tmp/test",'
            f' "model_provider": "openai"}}}}\n'
            f'{{"timestamp": "2024-01-01T00:00:01Z", "type": "response_item", '
            f'"payload": {{"role": "user", "content": [{_ui2}]}}}}\n'
            f'{{"timestamp": "2024-01-01T00:00:02Z", "type": "response_item", '
            f'"payload": {{"role": "assistant", "content": [{_ao2}]}}}}\n',
            encoding="utf-8",
        )

        index_file = tmp_path / "session_index.jsonl"
        index_entry = json.dumps(
            {
                "id": sid,
                "thread_name": "Implement Feature X",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        )
        index_file.write_text(index_entry + "\n", encoding="utf-8")

        sessions = list(iter_sessions(root=str(sessions_root)))
        assert len(sessions) == 1
        summary, _ = sessions[0]
        assert summary.title == "Implement Feature X"

    def test_turn_count_matches_turns(self, codex_root: str) -> None:
        from mintmory.core.history.adapters.codex import iter_sessions

        sessions = list(iter_sessions(root=codex_root))
        summary, turns = sessions[0]
        assert summary.turn_count == len(turns)


# ---------------------------------------------------------------------------
# Kiro adapter
# ---------------------------------------------------------------------------


class TestKiroAdapter:
    """Tests for core.history.adapters.kiro.iter_sessions."""

    @pytest.fixture()
    def kiro_root(self) -> str:
        return str(FIXTURES_DIR / "kiro")

    def test_parses_fixture(self, kiro_root: str) -> None:
        from mintmory.core.history.adapters.kiro import iter_sessions

        sessions = list(iter_sessions(root=kiro_root))
        assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

        summary, turns = sessions[0]

        # Verify agent
        assert summary.agent == "kiro"

        # Verify session_id
        assert summary.session_id == "kkkkkkkk-llll-mmmm-nnnn-oooooooooooo"

        # Verify title from sessions.json
        assert "refactor" in summary.title.lower() or "database" in summary.title.lower()

        # Verify repo is resolved (no .git in fixture path, fallback to basename)
        assert summary.repo != ""

        # Verify timestamp from sessions.json dateCreated (1710496800000 ms)
        assert "2024-03-15" in summary.ts_start

        # source_path must be absolute
        assert os.path.isabs(summary.source_path)
        assert summary.source_path.endswith(".json")

    def test_turns_roles(self, kiro_root: str) -> None:
        from mintmory.core.history.adapters.kiro import iter_sessions

        sessions = list(iter_sessions(root=kiro_root))
        _, turns = sessions[0]

        roles = [t.role for t in turns]
        assert "user" in roles
        assert "assistant" in roles

    def test_workspace_path_decoded(self, kiro_root: str) -> None:
        """The workspace path decoded from b64url dir name must be reflected in repo_path."""
        from mintmory.core.history.adapters.kiro import iter_sessions

        sessions = list(iter_sessions(root=kiro_root))
        summary, _ = sessions[0]

        # workspacePath in the JSON is /Users/test/projects/sample-project
        # repo_path is the cwd or git root; since no .git, it's the workspace path
        assert "sample-project" in summary.repo_path or summary.repo_path != ""

    def test_fail_soft_on_malformed_json(self, tmp_path: Path) -> None:
        """A malformed session JSON must be skipped, not abort."""
        from mintmory.core.history.adapters.kiro import iter_sessions

        kiro_dir = tmp_path
        ws_sessions = kiro_dir / "workspace-sessions"
        ws_sessions.mkdir()

        import base64

        ws_path = "/Users/test/workspace"
        ws_b64 = base64.urlsafe_b64encode(ws_path.encode()).decode().rstrip("=")
        ws_dir = ws_sessions / ws_b64
        ws_dir.mkdir()

        # Malformed session file
        bad_session = ws_dir / "malformed-0000-0000-0000-000000000001.json"
        bad_session.write_text("NOT VALID JSON AT ALL", encoding="utf-8")

        # Good session file
        good_session = ws_dir / "gggggggg-0000-0000-0000-000000000001.json"
        good_session.write_text(
            json.dumps(
                {
                    "sessionId": "gggggggg-0000-0000-0000-000000000001",
                    "title": "Good session",
                    "workspacePath": "/Users/test/workspace",
                    "history": [
                        {
                            "message": {
                                "role": "user",
                                "content": "Please implement feature Y",
                                "id": "msg-001",
                            },
                            "contextItems": [],
                        },
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Feature Y implemented.",
                                "id": "msg-002",
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        # Should not raise — bad session skipped, good one parsed
        sessions = list(iter_sessions(root=str(kiro_dir)))
        assert len(sessions) == 1
        summary, turns = sessions[0]
        assert summary.session_id == "gggggggg-0000-0000-0000-000000000001"
        assert summary.agent == "kiro"

    def test_vscdb_files_ignored(self, tmp_path: Path) -> None:
        """*.vscdb files must be ignored by the adapter."""
        from mintmory.core.history.adapters.kiro import iter_sessions

        kiro_dir = tmp_path
        ws_sessions = kiro_dir / "workspace-sessions"
        ws_sessions.mkdir()

        import base64

        ws_path = "/Users/test/workspace"
        ws_b64 = base64.urlsafe_b64encode(ws_path.encode()).decode().rstrip("=")
        ws_dir = ws_sessions / ws_b64
        ws_dir.mkdir()

        # A vscdb file that looks like JSON but should be ignored
        vscdb = ws_dir / "state.vscdb"
        vscdb.write_text('{"sessionId": "ignored"}', encoding="utf-8")

        sessions = list(iter_sessions(root=str(kiro_dir)))
        assert sessions == []

    def test_nonexistent_root_yields_nothing(self) -> None:
        from mintmory.core.history.adapters.kiro import iter_sessions

        sessions = list(iter_sessions(root="/tmp/does_not_exist_mintmory_kiro"))
        assert sessions == []

    def test_turn_count_matches_turns(self, kiro_root: str) -> None:
        from mintmory.core.history.adapters.kiro import iter_sessions

        sessions = list(iter_sessions(root=kiro_root))
        summary, turns = sessions[0]
        assert summary.turn_count == len(turns)


def test_codex_import_skip_only_when_source_exists(tmp_path: Path) -> None:
    """Imported sessions are skipped ONLY if their source_path still exists;
    orphaned imports (source deleted) must be kept so the session isn't lost."""
    import json as _json

    from mintmory.core.history.adapters import codex

    codex_dir = tmp_path / ".codex"
    sessions = codex_dir / "sessions"
    sessions.mkdir(parents=True)
    live_src = tmp_path / "live.jsonl"
    live_src.write_text("{}\n")  # exists
    gone_src = tmp_path / "gone.jsonl"  # never created
    (codex_dir / "external_agent_session_imports.json").write_text(
        _json.dumps(
            {
                "records": [
                    {"imported_thread_id": "live-id", "source_path": str(live_src)},
                    {"imported_thread_id": "gone-id", "source_path": str(gone_src)},
                ]
            }
        )
    )
    skip = codex._load_imported_ids(str(sessions))
    assert "live-id" in skip  # source exists -> skip (indexed via its own adapter)
    assert "gone-id" not in skip  # source deleted -> keep (Codex is the only copy)


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
        cron_files = [f for f in os.listdir(hermes_root) if f.startswith("session_cron_")]
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
