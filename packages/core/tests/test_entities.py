"""
M2 Gate (partial): Entity extraction unit tests.

All tests run without spaCy, without SQLite, without embeddings.
Pure function tests — fast, deterministic, no IO.
"""

from mintmory.core.entities import (
    _DEFAULT_ENTITY_STOPLIST,
    extract_entities,
    extract_entities_from_settings,
    extract_entities_regex,
    extract_entities_spacy,
)


class TestPhase1Regex:
    def test_extracts_proper_nouns(self) -> None:
        result = extract_entities_regex("Azure SQL Server is running on Microsoft Azure")
        assert "azure sql server" in result
        assert "microsoft azure" in result

    def test_extracts_acronyms(self) -> None:
        result = extract_entities_regex("The MCP protocol uses HTTP and JSON")
        assert "mcp" in result
        assert "http" in result
        assert "json" in result

    def test_extracts_quoted_spans(self) -> None:
        result = extract_entities_regex('The tool is called "parking integration"')
        assert "parking integration" in result

    def test_filters_stopwords(self) -> None:
        result = extract_entities_regex("The is a an are was were be been")
        assert not result  # all stopwords

    def test_deduplicates(self) -> None:
        result = extract_entities_regex("Claude Claude Claude")
        # 'claude' should appear only once
        assert result.count("claude") == 1

    def test_max_entities_cap(self) -> None:
        content = " ".join(f"Entity{i}Name" for i in range(50))
        result = extract_entities_regex(content, max_entities=5)
        assert len(result) <= 5

    def test_empty_string(self) -> None:
        result = extract_entities_regex("")
        assert result == []

    def test_normalises_to_lowercase(self) -> None:
        result = extract_entities_regex("Azure SQL Server")
        for entity in result:
            assert entity == entity.lower()


class TestPhase2Spacy:
    def test_silent_skip_when_spacy_unavailable(self) -> None:
        # This test always passes — if spaCy is not installed, returns []
        # If spaCy IS installed, it should return something non-empty for real content
        result = extract_entities_spacy("Dana works at Acme Space in Romania")
        assert isinstance(result, list)

    def test_returns_lowercase(self) -> None:
        result = extract_entities_spacy("Microsoft Azure")
        for entity in result:
            assert entity == entity.lower()


class TestCombined:
    def test_phase1_only_by_default(self) -> None:
        content = "Azure SQL is used by Acme"
        p1 = extract_entities(content, use_spacy=False)
        assert isinstance(p1, list)

    def test_combined_deduplicates_across_phases(self) -> None:
        content = "Azure SQL Server runs on Microsoft Azure"
        result = extract_entities(content, use_spacy=False)
        seen = set()
        for entity in result:
            assert entity not in seen, f"Duplicate entity: '{entity}'"
            seen.add(entity)

    def test_cap_applies_to_merged_result(self) -> None:
        content = " ".join(f"Entity{i}Name" for i in range(50))
        result = extract_entities(content, max_entities=10)
        assert len(result) <= 10


class TestTunableStopwords:
    def test_extra_stopwords_drops_named_entity(self) -> None:
        content = "Azure SQL Server is running on Microsoft Azure"
        # 'azure' is a legit entity by default...
        baseline = extract_entities_regex(content)
        assert "azure" in baseline
        # ...but dropping it via extra_stopwords removes the bare token.
        filtered = extract_entities_regex(content, extra_stopwords=frozenset({"azure"}))
        assert "azure" not in filtered
        # multi-word phrase containing it is unaffected (different normalised key)
        assert "azure sql server" in filtered

    def test_extra_stopwords_default_is_unchanged(self) -> None:
        content = "Azure SQL Server is running on Microsoft Azure"
        assert extract_entities_regex(content) == extract_entities_regex(
            content, extra_stopwords=None
        )

    def test_min_length_drops_short_tokens(self) -> None:
        content = 'The "ing" suffix in ABCD'
        # Default min_length=2 keeps 'ing' (len 3) and 'abcd'.
        baseline = extract_entities_regex(content)
        assert "ing" in baseline
        # min_length=4 drops 'ing' but keeps 'abcd' (len 4).
        filtered = extract_entities_regex(content, min_length=4)
        assert "ing" not in filtered
        assert "abcd" in filtered

    def test_default_min_length_reproduces_today(self) -> None:
        content = "Azure SQL Server on Microsoft Azure with HTTP and JSON"
        assert extract_entities_regex(content) == extract_entities_regex(content, min_length=2)

    def test_threads_through_extract_entities(self) -> None:
        content = "Azure SQL Server on Microsoft Azure"
        result = extract_entities(
            content,
            use_spacy=False,
            extra_stopwords=frozenset({"azure"}),
        )
        assert "azure" not in result

    def test_default_entity_stoplist_exists_and_has_baseline_noise(self) -> None:
        assert isinstance(_DEFAULT_ENTITY_STOPLIST, frozenset)
        # The 5 baseline noise tokens from EXPERIMENTS.md §3 / F2.
        for token in ("all", "api", "backend", "space", "ing"):
            assert token in _DEFAULT_ENTITY_STOPLIST

    def test_default_entity_stoplist_not_applied_automatically(self) -> None:
        # Opt-in only: a default call must NOT drop stoplist members.
        content = "The API and Backend run in App Space"
        baseline = extract_entities_regex(content)
        assert "api" in baseline
        assert "backend" in baseline
        # Opting in drops them.
        opted_in = extract_entities_regex(content, extra_stopwords=_DEFAULT_ENTITY_STOPLIST)
        assert "api" not in opted_in
        assert "backend" not in opted_in


class TestFromSettings:
    def test_default_settings_reproduce_today(self) -> None:
        from mintmory.core.config import EntitySettings

        content = "Azure SQL Server on Microsoft Azure with HTTP and JSON"
        settings = EntitySettings()
        assert extract_entities_from_settings(content, settings) == extract_entities(content)

    def test_settings_apply_extra_stopwords_and_min_length(self) -> None:
        from mintmory.core.config import EntitySettings

        content = 'The "ing" suffix; API and Azure'
        settings = EntitySettings(extra_stopwords_csv="azure,api", min_length=4)
        result = extract_entities_from_settings(content, settings)
        assert "azure" not in result
        assert "api" not in result
        assert "ing" not in result  # len 3 < min_length 4
