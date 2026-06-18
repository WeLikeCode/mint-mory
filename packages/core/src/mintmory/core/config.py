"""
Central, env-driven configuration for MintMory — the single source for every
tunable knob (embedding, concept-linking, entity filtering, L3 summaries, the LLM
backend, and OpenTelemetry).

Design rules (see docs/EXPERIMENTS.md and docs/OBSERVABILITY.md):
  * One module, built on pydantic-settings (already a core dependency).
  * Every default REPRODUCES today's behaviour, so importing/adopting this module
    is a no-op until an experiment overrides a value via env. That makes each knob
    a tracked experiment: flip one env var, measure, record the verdict.
  * The ONLY external dependency MintMory permits is the LLM backend (summaries +
    contradiction resolution); it lives behind ``LLMSettings`` and defaults to
    ``provider=none`` (fully offline — L3 + resolution skipped).
  * Embeddings default to the pure-Python in-process ``hashing`` provider (no
    Ollama, no torch); other providers are opt-in.

Each group is an independent ``BaseSettings`` with its own ``MINTMORY_<GROUP>_``
env prefix, so callers instantiate only what they need. List-like knobs are taken
as comma-separated strings (env-friendly) and exposed as parsed sets via helper
properties.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv_set(value: str) -> frozenset[str]:
    """Parse a comma-separated env string into a normalised lowercase set."""
    return frozenset(tok.strip().lower() for tok in value.split(",") if tok.strip())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class EmbeddingProvider(str, Enum):
    HASHING = "hashing"  # default — pure-Python, in-process, numpy-only
    LOCAL = "local"  # sentence-transformers (optional [local] extra)
    OLLAMA = "ollama"  # Ollama /v1/embeddings (optional, network)
    OPENAI = "openai"  # OpenAI embeddings (optional [openai] extra)
    FAKE = "fake"  # deterministic test embedder


class LLMProvider(str, Enum):
    NONE = "none"  # default — no LLM; L3 + contradiction resolution skipped
    OLLAMA = "ollama"  # OpenAI-compatible local endpoint (Ollama/LM Studio/vLLM)
    OPENAI = "openai"  # OpenAI / any OpenAI-compatible hosted endpoint


# ---------------------------------------------------------------------------
# Embeddings (MINTMORY_EMBED_*)
# ---------------------------------------------------------------------------
class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_EMBED_", extra="ignore")

    provider: EmbeddingProvider = EmbeddingProvider.HASHING
    dim: int = Field(default=512, ge=64, le=4096)
    word_ngram_min: int = Field(default=1, ge=1, le=3)
    word_ngram_max: int = Field(default=2, ge=1, le=4)
    char_ngram_min: int = Field(default=3, ge=0, le=6)  # 0 disables char n-grams
    char_ngram_max: int = Field(default=5, ge=0, le=8)
    use_idf: bool = False  # ship off first (pure function of text); see EXPERIMENTS.md E-E4
    # provider-specific (ollama/openai/local):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


# ---------------------------------------------------------------------------
# Concept linking (MINTMORY_LINK_*) — dreaming step 2. Defaults = today's graph.
# ---------------------------------------------------------------------------
class LinkSettings(BaseSettings):
    """Concept-linking (dreaming step 2). Defaults are the experiment-validated
    "E-L-MID" profile (docs/EXPERIMENTS.md §6.2): on the agentic_support corpus this
    cut links 2586->641 (-75%), search-around breadth 90%->46%, and noise entities
    5->0, with retrieval recall preserved (AXIS recall stayed 1.0, unlike the
    over-aggressive df_cap=0.15 variant which dropped it to 0.2 — REVERTED).
    Override any knob via MINTMORY_LINK_* env; set min_shared_entities=1 for tiny
    stores where a single shared entity is still a meaningful signal."""

    model_config = SettingsConfigDict(env_prefix="MINTMORY_LINK_", extra="ignore")

    min_shared_entities: int = Field(default=2, ge=1, le=8)
    # df_cap stays off (1.0): the 0.15 variant over-pruned and dropped recall (E-L6, REVERTED).
    entity_df_cap_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    max_per_node: int = Field(default=25, ge=0)  # 0 = unbounded
    idf_weighted_strength: bool = True
    min_jaccard: float = Field(default=0.0, ge=0.0, le=1.0)  # 0.0 = off
    stoplist_csv: str = "all,api,backend,ing,space"  # generic boilerplate excluded from linking
    # Hub-aware pruning (LEANN-informed): give high-degree "hub" concepts a larger
    # degree budget so a uniform cap can't sever the links that hold a cluster
    # together. Defaults are a NO-OP (multiplier 1.0 == today's uniform cap).
    hub_cap_multiplier: float = Field(default=1.0, ge=1.0, le=8.0)
    hub_degree_percentile: float = Field(default=0.9, ge=0.5, le=1.0)

    @property
    def stoplist(self) -> frozenset[str]:
        return _csv_set(self.stoplist_csv)


# ---------------------------------------------------------------------------
# Entity extraction / filtering (MINTMORY_ENTITY_*)
# ---------------------------------------------------------------------------
class EntitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_ENTITY_", extra="ignore")

    extra_stopwords_csv: str = ""  # extra entity stop-words (extraction-time)
    df_cap_ratio: float = Field(default=1.0, ge=0.0, le=1.0)  # 1.0 = off (consumption-time)
    min_length: int = Field(default=2, ge=1, le=8)

    @property
    def extra_stopwords(self) -> frozenset[str]:
        return _csv_set(self.extra_stopwords_csv)


# ---------------------------------------------------------------------------
# L3 summary policy (MINTMORY_SUMMARY_*) — dreaming step 3. Defaults = today.
# ---------------------------------------------------------------------------
class SummarySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_SUMMARY_", extra="ignore")

    top_k: int = Field(default=0, ge=0)  # 0 = uncapped (legacy: summarise all)
    min_memories: int = Field(default=3, ge=2)
    max_contents: int = Field(default=20, ge=1)
    max_content_chars: int = Field(default=0, ge=0)  # 0 = no truncation
    concurrency: int = Field(default=1, ge=1, le=16)  # parallel summary LLM calls (1 = serial)


# ---------------------------------------------------------------------------
# LLM backend (MINTMORY_LLM_*) — the only permitted external dependency.
# ---------------------------------------------------------------------------
class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_LLM_", extra="ignore")

    provider: LLMProvider = LLMProvider.NONE
    base_url: str = "http://localhost:11434/v1"  # OpenAI-compatible base
    model: str = "gemma4:e4b-it-qat"
    api_key: str | None = None
    timeout_s: float = Field(default=60.0, ge=1.0, le=600.0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_concurrency: int = Field(default=4, ge=1, le=32)

    @property
    def enabled(self) -> bool:
        return self.provider is not LLMProvider.NONE


# ---------------------------------------------------------------------------
# Document conversion (MINTMORY_CONVERT_*) — ingest-time binary→markdown.
# Defaults reproduce today's behaviour: auto-convert is gated by the CLI flag
# and the presence of the optional ``docs`` extra (markitdown imported lazily).
# ---------------------------------------------------------------------------
class ConversionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_CONVERT_", extra="ignore")

    enabled: bool = True  # global off-switch for auto-conversion (CLI --convert also gates)
    max_file_mb: float = Field(default=25.0, ge=0.0)  # on-disk size cap; 0 = no limit
    # Cap on the DECOMPRESSED markitdown output: max_file_mb is the on-disk
    # (compressed) size for zip/PDF formats, so it does NOT bound expansion.
    max_output_mb: float = Field(default=50.0, ge=0.0)  # 0 = no limit
    timeout_s: float = Field(default=120.0, ge=0.0)  # per-file conversion wall-clock; 0 = no bound
    extra_text_suffixes_csv: str = ""  # extra suffixes treated as plain text
    enable_plugins: bool = False  # markitdown 3rd-party plugins

    @property
    def extra_text_suffixes(self) -> frozenset[str]:
        """Extra plain-text suffixes: lowercase, single leading dot, blanks dropped."""
        return frozenset(f".{tok.lstrip('.')}" for tok in _csv_set(self.extra_text_suffixes_csv))

    @property
    def max_bytes(self) -> int | None:
        """On-disk byte cap derived from ``max_file_mb`` (None when <= 0, i.e. no limit)."""
        return None if self.max_file_mb <= 0 else int(self.max_file_mb * 1024 * 1024)

    @property
    def max_output_bytes(self) -> int | None:
        """Decompressed-output cap from ``max_output_mb`` (None when <= 0, no limit)."""
        return None if self.max_output_mb <= 0 else int(self.max_output_mb * 1024 * 1024)


# ---------------------------------------------------------------------------
# OpenTelemetry (MINTMORY_OTEL_*) — off by default, no-op shim when disabled.
# ---------------------------------------------------------------------------
class OTelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_OTEL_", extra="ignore")

    enabled: bool = False
    exporter: str = "console"  # "console" | "otlp"
    service_name: str = "mintmory"


# ---------------------------------------------------------------------------
# Personal notes (MINTMORY_NOTE_*) — capture + retrieval of user-authored notes.
# Defaults reproduce today's behaviour for non-note rows (note_bonus only ever
# applies to is_note=1; auto_include only adds ANNOTATES-linked notes).
# ---------------------------------------------------------------------------
class NoteSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_NOTE_", extra="ignore")

    # Additive authority boost in effective_score for is_note rows. Same scale as
    # the recency bonus (DECAY_BONUS_MAX = 0.1); a tie-breaker, not a hammer.
    note_bonus: float = Field(default=0.05, ge=0.0, le=1.0)
    # Max annotating notes auto-included per search result (reverse ANNOTATES
    # traversal). 0 disables auto-include.
    auto_include_cap: int = Field(default=3, ge=0, le=20)
    # Anchor resolution: minimum share of the candidate pool's relevance the top
    # candidate must hold to be treated as a confident/dominant hard-link match.
    anchor_min_dominance: float = Field(default=0.6, ge=0.0, le=1.0)


class Settings(BaseSettings):
    """Aggregate of every settings group. Each group still reads its own env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    embed: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    link: LinkSettings = Field(default_factory=LinkSettings)
    entity: EntitySettings = Field(default_factory=EntitySettings)
    summary: SummarySettings = Field(default_factory=SummarySettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    convert: ConversionSettings = Field(default_factory=ConversionSettings)
    otel: OTelSettings = Field(default_factory=OTelSettings)
    note: NoteSettings = Field(default_factory=NoteSettings)


def load_settings() -> Settings:
    """Build a fresh Settings from the current environment."""
    return Settings()
