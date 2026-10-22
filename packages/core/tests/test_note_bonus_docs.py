"""fix-note-bonus-env-name, task 3.2: the docs name the variable the code reads.

The behavioural half of the requirement ("`NoteSettings.note_bonus` SHALL be read
from `MINTMORY_NOTE_BONUS` ... and README and docs SHALL name `MINTMORY_NOTE_BONUS`")
is pinned in ``test_config.py``; this module pins the documentation half for
``docs/EXPERIMENTS.md``, whose personal-notes-knobs table still names only the
legacy ``MINTMORY_NOTE_NOTE_BONUS``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mintmory.core.config import NoteSettings

EXPERIMENTS_DOC = Path(__file__).resolve().parents[3] / "docs" / "EXPERIMENTS.md"


class TestNoteBonusDocumentedInExperiments:
    """docs/EXPERIMENTS.md names MINTMORY_NOTE_BONUS for the note-bonus knob."""

    @pytest.fixture(autouse=True)
    def _clear_note_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for variable in ("MINTMORY_NOTE_BONUS", "MINTMORY_NOTE_NOTE_BONUS"):
            monkeypatch.delenv(variable, raising=False)

    @pytest.mark.l4("C-4685d347")
    def test_experiments_documents_the_variable_config_reads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The documented name reaches the field, and the doc's bonus row uses it."""
        monkeypatch.setenv("MINTMORY_NOTE_BONUS", "0.1")
        assert NoteSettings().note_bonus == pytest.approx(0.1)

        text = EXPERIMENTS_DOC.read_text(encoding="utf-8")
        bonus_rows = [
            line
            for line in text.splitlines()
            if line.startswith("| `MINTMORY_NOTE_") and "BONUS" in line
        ]
        assert bonus_rows, "no note-bonus table row found in docs/EXPERIMENTS.md"
        assert all("MINTMORY_NOTE_BONUS" in row for row in bonus_rows), bonus_rows
