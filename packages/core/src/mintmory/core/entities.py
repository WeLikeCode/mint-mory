"""
Entity extraction — hybrid Phase-1 (regex, always-on) + Phase-2 (spaCy NER, optional).

Phase 1 (from widemem/extraction/entities.py — confirmed accurate by OPUS audit):
  Regex-based, zero dependencies:
    1. Capitalized proper nouns: r'\\b[A-Z][a-z]+(?:\\s+[A-Z][a-z]+)+\\b'
    2. All-caps acronyms: r'\\b[A-Z]{2,}s?\\b'
    3. Double-quoted spans: r'"([^"]+)"'
    4. Stopword filter
  Max 24 entities per memory.

Phase 2 (from Mem0 entity_extraction.py — confirmed spaCy en_core_web_sm by OPUS audit):
  Optional — only if spaCy + en_core_web_sm installed.
  4 types: PROPER, COMPOUND, QUOTED, NOUN.
  Silent skip if unavailable (same behaviour as Mem0's silent-skip-on-import-fail).

Design: Phase 1 always runs. Phase 2 extends the Phase-1 result set with
semantic entities regex misses (lowercase proper names, domain terms).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mintmory.core.config import EntitySettings

# ---------------------------------------------------------------------------
# Stopword list (common English words that are not useful entities)
# ---------------------------------------------------------------------------
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "and",
        "but",
        "or",
        "nor",
        "for",
        "yet",
        "so",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "they",
        "them",
        "their",
        "we",
        "our",
        "you",
        "your",
        "i",
        "my",
        "he",
        "she",
        "his",
        "her",
        "which",
        "who",
        "whom",
        "where",
        "when",
        "how",
        "what",
        "why",
        "not",
        "no",
        "yes",
        "more",
        "less",
        "also",
        "both",
        "each",
        "few",
        "some",
        "such",
        "same",
        "other",
        "another",
        "there",
        "here",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "about",
        "with",
        "without",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "because",
        "while",
        "although",
        "however",
    }
)

# ---------------------------------------------------------------------------
# Default tech / boilerplate entity stop-list (docs/EXPERIMENTS.md §3.1, F2).
#
# These are generic domain/boilerplate tokens that pollute the entity set
# (and downstream concept links + L3 summaries) without being discriminating
# entities. This set is kept DISTINCT from ``_STOPWORDS`` (the FTS-style
# English stopword concern) and is NOT applied automatically — applying it by
# default would change existing extraction output. Callers opt in by passing it
# (or a superset) via ``extra_stopwords`` (typically sourced from
# ``EntitySettings.extra_stopwords``).
# ---------------------------------------------------------------------------
_DEFAULT_ENTITY_STOPLIST: frozenset[str] = frozenset(
    {
        "all",
        "api",
        "backend",
        "frontend",
        "app",
        "ui",
        "ux",
        "db",
        "sdk",
        "cli",
        "http",
        "json",
        "space",
        "ing",
    }
)

# ---------------------------------------------------------------------------
# Phase-1 regex patterns
#
# We extract at two granularities so that both multi-word concepts and the
# individual tokens that compose them become entities:
#   • _RE_CAP_PHRASE — runs of 1–4 capitalised / ALL-CAPS words, e.g.
#     "Azure SQL Server", "Microsoft Azure" (acronyms like SQL are kept in-phrase).
#   • _RE_CAP_WORD   — each capitalised / ALL-CAPS token on its own, e.g.
#     "Azure", "SQL", "Claude", "MCP", "HTTP".
#   • _RE_QUOTED     — anything inside double quotes (lower-case concepts too).
# finditer is non-overlapping, so the phrase pass yields the long spans and the
# word pass yields the constituent tokens; both feed a single dedup pass.
# ---------------------------------------------------------------------------
_RE_CAP_PHRASE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3}\b")
_RE_CAP_WORD = re.compile(r"\b[A-Z][A-Za-z0-9]*\b")
_RE_QUOTED = re.compile(r'"([^"]{2,50})"')


def extract_entities_regex(
    content: str,
    max_entities: int = 24,
    extra_stopwords: frozenset[str] | None = None,
    min_length: int = 2,
) -> list[str]:
    """
    Phase-1 entity extraction. Zero dependencies, always runs.

    Returns a deduplicated list of lowercase-normalised entity strings,
    capped at max_entities. Extracts both capitalised phrases and the
    individual capitalised/acronym tokens that compose them, plus quoted spans.

    Args:
        content: Memory content string.
        max_entities: Maximum entities to return (default 24, matching widemem).
        extra_stopwords: Optional extra stop-words dropped in ADDITION to the
            built-in ``_STOPWORDS`` (e.g. ``_DEFAULT_ENTITY_STOPLIST`` or a
            curated set from ``EntitySettings``). ``None`` (default) reproduces
            today's behaviour.
        min_length: Drop normalised entities shorter than this many characters.
            Default 2 reproduces today's behaviour.
    """
    stoplist = _STOPWORDS if extra_stopwords is None else (_STOPWORDS | extra_stopwords)

    candidates: list[str] = []

    # Multi-word phrases first (so "azure sql server" ranks ahead of "azure").
    for match in _RE_CAP_PHRASE.finditer(content):
        candidates.append(match.group(0))

    # Individual capitalised / acronym tokens.
    for match in _RE_CAP_WORD.finditer(content):
        candidates.append(match.group(0))

    # Quoted spans (may be lower-case concepts the cap patterns miss).
    for match in _RE_QUOTED.finditer(content):
        candidates.append(match.group(1))

    normalised: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        key = raw.lower().strip()
        if key and len(key) >= min_length and key not in stoplist and key not in seen:
            seen.add(key)
            normalised.append(key)

    return normalised[:max_entities]


def extract_entities_spacy(
    content: str,
    max_entities: int = 24,
    extra_stopwords: frozenset[str] | None = None,
    min_length: int = 2,
) -> list[str]:
    """
    Phase-2 entity extraction using spaCy en_core_web_sm.
    Silent no-op if spaCy or the model is not installed (matches Mem0 behaviour).

    Returns lowercase-normalised entities to merge with Phase-1 results.

    Args:
        content: Memory content string.
        max_entities: Maximum entities to return (default 24).
        extra_stopwords: Optional extra stop-words dropped in ADDITION to the
            built-in ``_STOPWORDS``. ``None`` (default) reproduces today's
            behaviour.
        min_length: Drop normalised entities shorter than this many characters.
            Default 2 reproduces today's behaviour.
    """
    try:
        import spacy

        nlp = spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        return []

    stoplist = _STOPWORDS if extra_stopwords is None else (_STOPWORDS | extra_stopwords)

    doc = nlp(content[:5000])  # cap to avoid very large inputs
    entities: list[str] = []
    seen: set[str] = set()

    for ent in doc.ents:
        key = ent.text.lower().strip()
        if key and len(key) >= min_length and key not in stoplist and key not in seen:
            seen.add(key)
            entities.append(key)

    return entities[:max_entities]


def extract_entities(
    content: str,
    max_entities: int = 24,
    use_spacy: bool = False,
    extra_stopwords: frozenset[str] | None = None,
    min_length: int = 2,
) -> list[str]:
    """
    Combined Phase-1 + optional Phase-2 entity extraction.

    Args:
        content: Memory content string.
        max_entities: Maximum total entities to return (default 24, matching widemem).
        use_spacy: Enable Phase-2 spaCy extraction (requires en_core_web_sm installed).
        extra_stopwords: Optional extra stop-words dropped in ADDITION to the
            built-in ``_STOPWORDS`` (threaded into both phases). ``None``
            (default) reproduces today's behaviour.
        min_length: Drop normalised entities shorter than this many characters
            (threaded into both phases). Default 2 reproduces today's behaviour.

    Returns:
        Deduplicated list of lowercase entity strings.
    """
    phase1 = extract_entities_regex(
        content,
        max_entities=max_entities,
        extra_stopwords=extra_stopwords,
        min_length=min_length,
    )

    if not use_spacy:
        return phase1

    phase2 = extract_entities_spacy(
        content,
        max_entities=max_entities,
        extra_stopwords=extra_stopwords,
        min_length=min_length,
    )

    merged: list[str] = list(phase1)
    seen = set(phase1)
    for entity in phase2:
        if entity not in seen:
            seen.add(entity)
            merged.append(entity)

    return merged[:max_entities]


def extract_entities_from_settings(
    content: str,
    settings: EntitySettings,
    max_entities: int = 24,
    use_spacy: bool = False,
) -> list[str]:
    """
    Convenience wrapper applying ``EntitySettings`` extraction-time knobs.

    Reads ``settings.extra_stopwords`` and ``settings.min_length`` (see
    ``mintmory.core.config.EntitySettings``) and forwards them to
    :func:`extract_entities`. With default settings this reproduces today's
    behaviour (no extra stop-words, ``min_length=2``).
    """
    return extract_entities(
        content,
        max_entities=max_entities,
        use_spacy=use_spacy,
        extra_stopwords=settings.extra_stopwords,
        min_length=settings.min_length,
    )
