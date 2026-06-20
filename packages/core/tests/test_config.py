"""
Unit tests for MintMory config settings classes.

MM-22: SearchSettings (MINTMORY_SEARCH_* prefix) with vector_rrf_weight.
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
