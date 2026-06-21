"""
Unit tests for MintMory config settings classes.

MM-22: SearchSettings (MINTMORY_SEARCH_* prefix) with vector_rrf_weight.
MM-30: SegmentSettings + LLMSettings new fields (bound-llm-distiller).
MM-33: DocumentSettings (MINTMORY_DOC_* prefix).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestSearchSettings:
    """MM-22: SearchSettings with vector_rrf_weight."""

    def test_default_vector_rrf_weight_is_1(self) -> None:
        """SearchSettings() default vector_rrf_weight is 1.0."""
        from mintmory.core.config import SearchSettings

        s = SearchSettings()
        assert s.vector_rrf_weight == pytest.approx(1.0)

    def test_env_var_parses_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_SEARCH_VECTOR_RRF_WEIGHT=3.0 is read from environment."""
        from mintmory.core.config import SearchSettings

        monkeypatch.setenv("MINTMORY_SEARCH_VECTOR_RRF_WEIGHT", "3.0")
        s = SearchSettings()
        assert s.vector_rrf_weight == pytest.approx(3.0)

    def test_env_var_integer_string_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_SEARCH_VECTOR_RRF_WEIGHT=5 (integer string) also parses."""
        from mintmory.core.config import SearchSettings

        monkeypatch.setenv("MINTMORY_SEARCH_VECTOR_RRF_WEIGHT", "5")
        s = SearchSettings()
        assert s.vector_rrf_weight == pytest.approx(5.0)

    def test_lower_bound_zero_is_valid(self) -> None:
        """vector_rrf_weight=0.0 is at the lower bound (ge=0.0) and must be accepted."""
        from mintmory.core.config import SearchSettings

        s = SearchSettings(vector_rrf_weight=0.0)
        assert s.vector_rrf_weight == pytest.approx(0.0)

    def test_upper_bound_16_is_valid(self) -> None:
        """vector_rrf_weight=16.0 is at the upper bound (le=16.0) and must be accepted."""
        from mintmory.core.config import SearchSettings

        s = SearchSettings(vector_rrf_weight=16.0)
        assert s.vector_rrf_weight == pytest.approx(16.0)

    def test_below_lower_bound_raises(self) -> None:
        """vector_rrf_weight < 0.0 raises a validation error (ge=0.0)."""
        from mintmory.core.config import SearchSettings

        with pytest.raises(ValidationError):
            SearchSettings(vector_rrf_weight=-0.1)

    def test_above_upper_bound_raises(self) -> None:
        """vector_rrf_weight > 16.0 raises a validation error (le=16.0)."""
        from mintmory.core.config import SearchSettings

        with pytest.raises(ValidationError):
            SearchSettings(vector_rrf_weight=16.1)

    def test_env_below_lower_bound_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_SEARCH_VECTOR_RRF_WEIGHT=-1.0 raises validation error."""
        from mintmory.core.config import SearchSettings

        monkeypatch.setenv("MINTMORY_SEARCH_VECTOR_RRF_WEIGHT", "-1.0")
        with pytest.raises(ValidationError):
            SearchSettings()

    def test_env_above_upper_bound_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_SEARCH_VECTOR_RRF_WEIGHT=20.0 raises validation error."""
        from mintmory.core.config import SearchSettings

        monkeypatch.setenv("MINTMORY_SEARCH_VECTOR_RRF_WEIGHT", "20.0")
        with pytest.raises(ValidationError):
            SearchSettings()

    def test_env_prefix_is_mintmory_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only MINTMORY_SEARCH_* prefix is read (not MINTMORY_* without subgroup)."""
        from mintmory.core.config import SearchSettings

        # Setting without the prefix has no effect; default (1.0) is preserved.
        monkeypatch.setenv("VECTOR_RRF_WEIGHT", "7.0")
        monkeypatch.setenv("MINTMORY_VECTOR_RRF_WEIGHT", "7.0")
        s = SearchSettings()
        assert s.vector_rrf_weight == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# MM-30: SegmentSettings new fields (bound-llm-distiller)
# ---------------------------------------------------------------------------


class TestSegmentSettingsBounds:
    """MM-30: SegmentSettings.max_turn_chars, max_prompt_chars, distill_max_tokens."""

    def test_defaults(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings()
        assert s.max_turn_chars == 2000
        assert s.max_prompt_chars == 12000
        assert s.distill_max_tokens == 2048

    def test_max_turn_chars_lower_bound(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings(max_turn_chars=100)
        assert s.max_turn_chars == 100

    def test_max_turn_chars_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import SegmentSettings

        with pytest.raises(ValidationError):
            SegmentSettings(max_turn_chars=99)

    def test_max_turn_chars_upper_bound(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings(max_turn_chars=100_000)
        assert s.max_turn_chars == 100_000

    def test_max_turn_chars_above_upper_bound_raises(self) -> None:
        from mintmory.core.config import SegmentSettings

        with pytest.raises(ValidationError):
            SegmentSettings(max_turn_chars=100_001)

    def test_max_prompt_chars_lower_bound(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings(max_prompt_chars=500)
        assert s.max_prompt_chars == 500

    def test_max_prompt_chars_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import SegmentSettings

        with pytest.raises(ValidationError):
            SegmentSettings(max_prompt_chars=499)

    def test_distill_max_tokens_lower_bound(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings(distill_max_tokens=16)
        assert s.distill_max_tokens == 16

    def test_distill_max_tokens_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import SegmentSettings

        with pytest.raises(ValidationError):
            SegmentSettings(distill_max_tokens=15)

    def test_distill_max_tokens_upper_bound(self) -> None:
        from mintmory.core.config import SegmentSettings

        s = SegmentSettings(distill_max_tokens=8192)
        assert s.distill_max_tokens == 8192

    def test_distill_max_tokens_above_upper_bound_raises(self) -> None:
        from mintmory.core.config import SegmentSettings

        with pytest.raises(ValidationError):
            SegmentSettings(distill_max_tokens=8193)


class TestLLMSettingsMaxTokens:
    """MM-30: LLMSettings.max_tokens field."""

    def test_default_max_tokens_is_0(self) -> None:
        from mintmory.core.config import LLMSettings

        s = LLMSettings()
        assert s.max_tokens == 0

    def test_max_tokens_positive_value(self) -> None:
        from mintmory.core.config import LLMSettings

        s = LLMSettings(max_tokens=512)
        assert s.max_tokens == 512

    def test_max_tokens_upper_bound(self) -> None:
        from mintmory.core.config import LLMSettings

        s = LLMSettings(max_tokens=32000)
        assert s.max_tokens == 32000

    def test_max_tokens_above_upper_bound_raises(self) -> None:
        from mintmory.core.config import LLMSettings

        with pytest.raises(ValidationError):
            LLMSettings(max_tokens=32001)

    def test_max_tokens_negative_raises(self) -> None:
        from mintmory.core.config import LLMSettings

        with pytest.raises(ValidationError):
            LLMSettings(max_tokens=-1)


# ---------------------------------------------------------------------------
# MM-33: DocumentSettings (document recency + co-change)
# ---------------------------------------------------------------------------


class TestDocumentSettings:
    """MM-33: DocumentSettings with MINTMORY_DOC_* env prefix."""

    def test_defaults(self) -> None:
        """All defaults match the spec."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings()
        assert s.cochange_enabled is True
        assert s.weight_time == pytest.approx(1.0)
        assert s.weight_path == pytest.approx(0.5)
        assert s.weight_content == pytest.approx(0.5)
        assert s.tau_seconds == 3600
        assert s.min_cluster_size == 2
        assert s.use_embeddings is True

    def test_env_prefix_mintmory_doc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_DOC_* prefix is read."""
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_TAU_SECONDS", "7200")
        s = DocumentSettings()
        assert s.tau_seconds == 7200

    def test_cochange_enabled_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINTMORY_DOC_COCHANGE_ENABLED=false disables co-change."""
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_COCHANGE_ENABLED", "false")
        s = DocumentSettings()
        assert s.cochange_enabled is False

    def test_weight_time_lower_bound(self) -> None:
        """weight_time=0.0 is at the lower bound (ge=0.0)."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(weight_time=0.0)
        assert s.weight_time == pytest.approx(0.0)

    def test_weight_time_below_lower_bound_raises(self) -> None:
        """weight_time < 0.0 raises ValidationError."""
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(weight_time=-0.1)

    def test_weight_path_lower_bound(self) -> None:
        """weight_path=0.0 is valid."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(weight_path=0.0)
        assert s.weight_path == pytest.approx(0.0)

    def test_weight_content_lower_bound(self) -> None:
        """weight_content=0.0 is valid."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(weight_content=0.0)
        assert s.weight_content == pytest.approx(0.0)

    def test_tau_seconds_lower_bound(self) -> None:
        """tau_seconds=1 is at the lower bound (ge=1)."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(tau_seconds=1)
        assert s.tau_seconds == 1

    def test_tau_seconds_below_lower_bound_raises(self) -> None:
        """tau_seconds=0 raises ValidationError (ge=1)."""
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(tau_seconds=0)

    def test_min_cluster_size_lower_bound(self) -> None:
        """min_cluster_size=2 is at the lower bound (ge=2)."""
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(min_cluster_size=2)
        assert s.min_cluster_size == 2

    def test_min_cluster_size_below_lower_bound_raises(self) -> None:
        """min_cluster_size=1 raises ValidationError (ge=2)."""
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(min_cluster_size=1)

    def test_settings_aggregate_has_doc(self) -> None:
        """Settings() has a .doc field of type DocumentSettings."""
        from mintmory.core.config import DocumentSettings, Settings

        s = Settings()
        assert isinstance(s.doc, DocumentSettings)
        assert s.doc.cochange_enabled is True


class TestDocumentSettingsMM34:
    """MM-34: new DocumentSettings knobs."""

    def test_new_knob_defaults(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings()
        assert s.max_cochange_gap_seconds == 86_400
        assert s.max_cochange_cluster_size == 50
        assert s.cochange_exclude_images is True
        assert s.cochange_exclude_artifacts is True
        assert s.cochange_exclude_suffixes_csv == ""
        assert s.cochange_label_kind is True
        assert s.cochange_fallback_enabled is True
        assert s.cochange_fallback_max_n == 8
        assert s.cochange_distance_eps == pytest.approx(0.35)

    def test_max_cochange_gap_seconds_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(max_cochange_gap_seconds=1)
        assert s.max_cochange_gap_seconds == 1

    def test_max_cochange_gap_seconds_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(max_cochange_gap_seconds=0)

    def test_max_cochange_cluster_size_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(max_cochange_cluster_size=2)
        assert s.max_cochange_cluster_size == 2

    def test_max_cochange_cluster_size_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(max_cochange_cluster_size=1)

    def test_cochange_fallback_max_n_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_fallback_max_n=2)
        assert s.cochange_fallback_max_n == 2

    def test_cochange_fallback_max_n_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_fallback_max_n=1)

    def test_cochange_distance_eps_bounds(self) -> None:
        from mintmory.core.config import DocumentSettings

        s_low = DocumentSettings(cochange_distance_eps=0.0)
        assert s_low.cochange_distance_eps == pytest.approx(0.0)
        s_high = DocumentSettings(cochange_distance_eps=1.0)
        assert s_high.cochange_distance_eps == pytest.approx(1.0)

    def test_cochange_distance_eps_below_zero_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_distance_eps=-0.01)

    def test_cochange_distance_eps_above_one_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_distance_eps=1.01)

    def test_cochange_exclude_suffixes_empty(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv="")
        assert s.cochange_exclude_suffixes == frozenset()

    def test_cochange_exclude_suffixes_parsed(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv=".log,.TMP, .bak ")
        assert s.cochange_exclude_suffixes == frozenset({".log", ".tmp", ".bak"})

    def test_cochange_exclude_suffixes_no_leading_dot_gets_one(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv="log,tmp")
        assert ".log" in s.cochange_exclude_suffixes
        assert ".tmp" in s.cochange_exclude_suffixes

    def test_cochange_exclude_suffixes_blanks_dropped(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv=",.log,,")
        assert s.cochange_exclude_suffixes == frozenset({".log"})

    def test_env_prefix_doc_reads_new_knobs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_MAX_COCHANGE_GAP_SECONDS", "3600")
        monkeypatch.setenv("MINTMORY_DOC_COCHANGE_FALLBACK_ENABLED", "false")
        s = DocumentSettings()
        assert s.max_cochange_gap_seconds == 3600
        assert s.cochange_fallback_enabled is False
