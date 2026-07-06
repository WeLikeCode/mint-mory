"""
Golden-set retrieval baseline for MintMory — Phase 1.

Purpose
-------
Establishes a deterministic, thresholded recall baseline that every storage
backend MUST meet.  Phase 2's PostgresBackend must pass this same suite (the
postgres parameter auto-skips today and runs in Phase 2 CI).

Design
------
Corpus: 70 realistic memories across 7 topic clusters (10 memories each).
Every cluster uses a vocabulary that is isolated from other clusters so that
BM25 IDF weights are high for each cluster's distinctive terms.  Each needle
memory shares >=4 distinctive tokens with its golden query, making it dominant
in the BM25 ranking even before the vector phase contributes.

Embedder: deterministic ``HashingEmbedder(dim=64)`` — attached by the
``backend`` fixture.  Both the vector phase (when sqlite-vec is available) and
the FTS5 phase (always available) are exercised.  The recall guarantee is
designed to hold for FTS5-only operation so the test is backend-agnostic.

Recall metric
-------------
For each golden case ``(query, needle_memory_id)``, a "hit" is counted when
``needle_memory_id`` appears in the top-K search results.  The final metric is:

    recall@K = hits / total_cases

Threshold: recall@5 >= 0.70

    K = 5              — top-K window; 5 covers the main result page
    RECALL_THRESHOLD = 0.70   — >=70 % of golden cases must be hits

Rationale for K=5 and threshold=0.7:
  * With 4+ distinctive shared tokens between query and needle, and isolated
    cluster vocabularies across 70 corpus members, BM25 places the needle at
    rank 1-3 in the vast majority of cases.
  * A threshold of 0.7 requires ceil(0.70 × 11) = 8 out of 11 golden cases
    to hit, absorbing up to 3 edge-case misses (e.g. rare porter-stemmer
    interactions that collapse two different stems) while still being
    meaningfully discriminative.
  * Phase 2 must meet the SAME threshold on PostgresBackend to prove that
    tsvector/ts_rank parity with SQLite FTS5 is within the bounded drift
    described in design.md §6.1.

Determinism guarantee
---------------------
All IDs are fixed strings assigned at corpus-build time (not random UUIDs) so
the needle ID for each golden case is known before any INSERT is issued.  The
HashingEmbedder is stable across processes and platforms.  No RNG, no time
dependence, no network calls.
"""

from __future__ import annotations

from typing import Any

from mintmory.core.ports import StorageBackend
from mintmory.core.types import MemoryCategory, MemoryRecord, MemorySource, SearchRequest

from conformance import BackendHandle

# ---------------------------------------------------------------------------
# Constants (inline so tests are self-documenting)
# ---------------------------------------------------------------------------

TOP_K: int = 5
RECALL_THRESHOLD: float = 0.70

# ---------------------------------------------------------------------------
# Corpus: 70 memories across 7 topic clusters (10 per cluster)
#
# Design rules:
#   * Every cluster has a distinctive vocabulary (no cross-cluster token
#     overlap for the distinctive terms used in golden queries).
#   * The needle memory for each golden query shares >=4 of the query tokens.
#   * IDs are fixed so the golden-case needle_id is known statically.
# ---------------------------------------------------------------------------

# fmt: off
CORPUS: list[dict[str, Any]] = [
    # -------------------------------------------------------------------
    # Cluster 1: Kubernetes / container orchestration
    # -------------------------------------------------------------------
    {"id": "k8s-needle-01", "content":
        "kubernetes autoscaling pods cpu replicas hpa deployment target utilization",
     "category": "fact"},
    {"id": "k8s-02", "content":
        "kubectl apply namespace manifest yaml resource deployment rollout",
     "category": "fact"},
    {"id": "k8s-03", "content":
        "kubernetes pod scheduling affinity taint toleration eviction node",
     "category": "fact"},
    {"id": "k8s-04", "content":
        "kubernetes service clusterip loadbalancer nodeport selector label port",
     "category": "fact"},
    {"id": "k8s-05", "content":
        "kubernetes persistent volume claim pvc storageclass retention delete",
     "category": "fact"},
    {"id": "k8s-needle-06", "content":
        "kubernetes ingress nginx annotation routing path ssl tls certificate controller",
     "category": "fact"},
    {"id": "k8s-07", "content":
        "kubernetes configmap secret env variable mount volume pod container",
     "category": "fact"},
    {"id": "k8s-08", "content":
        "kubernetes rbac serviceaccount role rolebinding permission cluster",
     "category": "fact"},
    {"id": "k8s-09", "content":
        "kubernetes helm chart release upgrade rollback repository index artifact",
     "category": "fact"},
    {"id": "k8s-10", "content":
        "kubernetes liveness readiness probe healthcheck endpoint startup failure",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 2: Database / SQL / persistence
    # -------------------------------------------------------------------
    {"id": "db-needle-01", "content":
        "postgresql connection pool pgbouncer transaction mode idle timeout reuse",
     "category": "fact"},
    {"id": "db-02", "content":
        "sql query optimization index btree scan explain analyze sequential heap",
     "category": "fact"},
    {"id": "db-03", "content":
        "database migration alembic schema upgrade downgrade revision history",
     "category": "fact"},
    {"id": "db-04", "content":
        "postgresql replication primary replica streaming wal checkpoint archive",
     "category": "fact"},
    {"id": "db-05", "content":
        "redis cache expiry ttl eviction lru maxmemory policy keyspace notification",
     "category": "fact"},
    {"id": "db-06", "content":
        "sqlite wal journal checkpoint busy timeout exclusive lock concurrent",
     "category": "fact"},
    {"id": "db-07", "content":
        "database transaction isolation serializable repeatable read commit rollback",
     "category": "fact"},
    {"id": "db-needle-09", "content":
        "postgresql jsonb column operator gin index extract nested path query",
     "category": "fact"},
    {"id": "db-08", "content":
        "sql join inner outer left right cross foreign key constraint referential",
     "category": "fact"},
    {"id": "db-10", "content":
        "database backup restore dump pitr point recovery snapshot retention policy",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 3: Python development / tooling
    # -------------------------------------------------------------------
    {"id": "py-needle-01", "content":
        "python type hints mypy annotation strict protocol runtime check generic",
     "category": "fact"},
    {"id": "py-02", "content":
        "pytest fixture parametrize mark skip conftest asyncio session scope",
     "category": "fact"},
    {"id": "py-needle-03", "content":
        "python asyncio event loop coroutine await task gather concurrent future",
     "category": "fact"},
    {"id": "py-04", "content":
        "python dataclass pydantic model validation field default factory frozen",
     "category": "fact"},
    {"id": "py-05", "content":
        "python packaging pyproject toml uv pip install dependency extras wheel",
     "category": "fact"},
    {"id": "py-06", "content":
        "python logging handler level format debug warning critical propagate",
     "category": "fact"},
    {"id": "py-07", "content":
        "python pathlib path read write glob iterdir mkdir parents exist",
     "category": "fact"},
    {"id": "py-08", "content":
        "python context manager with statement enter exit cleanup resource close",
     "category": "fact"},
    {"id": "py-09", "content":
        "python generator yield lazy iterator memory efficient stream pipeline",
     "category": "fact"},
    {"id": "py-10", "content":
        "python multiprocessing pool thread lock concurrent future executor submit",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 4: Security / authentication / secrets
    # -------------------------------------------------------------------
    {"id": "sec-needle-01", "content":
        "jwt token bearer authentication oauth2 scope claim expiry refresh grant",
     "category": "fact"},
    {"id": "sec-02", "content":
        "tls ssl certificate authority chain verify hostname fingerprint revoke",
     "category": "fact"},
    {"id": "sec-03", "content":
        "api key header authorization hmac signature rate limit throttle",
     "category": "fact"},
    {"id": "sec-04", "content":
        "password hash bcrypt argon2 salt pepper stretch iterations derive",
     "category": "fact"},
    {"id": "sec-05", "content":
        "ssh keypair private public rsa ed25519 authorized_keys agent forward",
     "category": "fact"},
    {"id": "sec-06", "content":
        "firewall iptables allow deny inbound outbound rule chain policy filter",
     "category": "fact"},
    {"id": "sec-07", "content":
        "csrf xss injection sanitize escape html input validation prevent attack",
     "category": "fact"},
    {"id": "sec-08", "content":
        "secrets manager vault rotate inject environment variable encrypted store",
     "category": "fact"},
    {"id": "sec-09", "content":
        "mfa totp qr code authenticator second factor otp time-based verify",
     "category": "fact"},
    {"id": "sec-10", "content":
        "network acl vpc subnet cidr route table egress ingress security group",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 5: Observability / monitoring / tracing
    # -------------------------------------------------------------------
    {"id": "obs-needle-01", "content":
        "prometheus metrics gauge counter histogram scrape target job interval",
     "category": "fact"},
    {"id": "obs-02", "content":
        "grafana dashboard panel query datasource alert notification channel rule",
     "category": "fact"},
    {"id": "obs-needle-03", "content":
        "opentelemetry trace span exporter jaeger zipkin collector propagation otel",
     "category": "fact"},
    {"id": "obs-04", "content":
        "log aggregation elasticsearch kibana fluentd indexing retention shard",
     "category": "fact"},
    {"id": "obs-05", "content":
        "slo sli error budget burn rate availability percentile latency uptime",
     "category": "fact"},
    {"id": "obs-06", "content":
        "alertmanager pagerduty routing silencing inhibit receiver escalation group",
     "category": "fact"},
    {"id": "obs-07", "content":
        "distributed tracing context propagation header baggage parent child link",
     "category": "fact"},
    {"id": "obs-08", "content":
        "metric cardinality label dimension tag timeseries retention downsample",
     "category": "fact"},
    {"id": "obs-09", "content":
        "health check readiness liveness probe startup endpoint kubelet poll",
     "category": "fact"},
    {"id": "obs-10", "content":
        "incident postmortem timeline runbook on-call escalation mitigation review",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 6: Git / version control
    # -------------------------------------------------------------------
    {"id": "git-needle-01", "content":
        "git branch merge rebase conflict resolution squash commit interactive",
     "category": "fact"},
    {"id": "git-02", "content":
        "git remote push pull fetch origin upstream clone bare mirror",
     "category": "fact"},
    {"id": "git-03", "content":
        "git stash pop apply save restore worktree checkout detach",
     "category": "fact"},
    {"id": "git-04", "content":
        "git bisect blame annotate log history diff patch hunk range",
     "category": "fact"},
    {"id": "git-05", "content":
        "git submodule recursive update init sparse checkout shallow depth",
     "category": "fact"},
    {"id": "git-06", "content":
        "github actions workflow trigger dispatch artifact upload cache runner",
     "category": "fact"},
    {"id": "git-07", "content":
        "git tag annotated lightweight release signed semantic version changelog",
     "category": "fact"},
    {"id": "git-08", "content":
        "git hook pre-commit pre-push lint format validate enforce quality gate",
     "category": "fact"},
    {"id": "git-09", "content":
        "pull request review approve merge squash rebase code suggestion inline",
     "category": "fact"},
    {"id": "git-10", "content":
        "git cherry-pick patch apply transplant commit range upstream backport",
     "category": "fact"},

    # -------------------------------------------------------------------
    # Cluster 7: REST API / HTTP / microservices
    # -------------------------------------------------------------------
    {"id": "api-needle-01", "content":
        "rest api http status codes json response body request header method",
     "category": "fact"},
    {"id": "api-02", "content":
        "openapi swagger specification endpoint path operation schema component",
     "category": "fact"},
    {"id": "api-03", "content":
        "grpc protobuf service method stream unary bidirectional deadline metadata",
     "category": "fact"},
    {"id": "api-04", "content":
        "graphql query mutation subscription resolver type schema federation",
     "category": "fact"},
    {"id": "api-05", "content":
        "circuit breaker retry backoff timeout resilience fallback bulkhead pattern",
     "category": "fact"},
    {"id": "api-06", "content":
        "service mesh istio sidecar envoy traffic management policy observability",
     "category": "fact"},
    {"id": "api-07", "content":
        "cors preflight origin allowed header credential browser cross-origin",
     "category": "fact"},
    {"id": "api-08", "content":
        "pagination cursor offset limit next previous total count response header",
     "category": "fact"},
    {"id": "api-09", "content":
        "webhook event delivery signature validation retry idempotent payload",
     "category": "fact"},
    {"id": "api-10", "content":
        "content negotiation accept media type version header negotiate response",
     "category": "fact"},
]
# fmt: on

# ---------------------------------------------------------------------------
# Golden cases: (query_text, needle_memory_id, description)
#
# The needle_memory_id matches the "id" field in CORPUS above.  The query
# shares >=4 distinctive tokens with the needle content so FTS5 BM25 places
# the needle at rank 1-3 for an isolated-vocabulary cluster.
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[tuple[str, str, str]] = [
    # query                                       needle_id           description
    ("kubernetes autoscaling hpa replicas cpu", "k8s-needle-01", "k8s HPA autoscaling"),
    ("kubernetes ingress nginx routing ssl", "k8s-needle-06", "k8s ingress nginx"),
    ("postgresql pgbouncer connection pool", "db-needle-01", "PG connection pool"),
    ("postgresql jsonb gin index operator", "db-needle-09", "PG JSONB gin"),
    ("python mypy type hints annotation", "py-needle-01", "python mypy types"),
    ("python asyncio coroutine await gather", "py-needle-03", "python asyncio"),
    ("jwt oauth bearer token scope claim", "sec-needle-01", "JWT oauth2"),
    ("prometheus metrics scrape counter gauge", "obs-needle-01", "prometheus metrics"),
    ("opentelemetry trace span exporter jaeger", "obs-needle-03", "otel tracing"),
    ("git merge rebase branch conflict squash", "git-needle-01", "git merge rebase"),
    ("rest api http status codes json", "api-needle-01", "REST HTTP codes"),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_corpus(b: StorageBackend) -> dict[str, str]:
    """Insert all corpus memories into backend ``b`` using fixed IDs.

    Returns a mapping of ``corpus_id -> actual_stored_id`` (they are equal
    since IDs are supplied via ``MemoryRecord(id=...)``, but the map documents
    the correspondence explicitly).
    """
    id_map: dict[str, str] = {}
    for entry in CORPUS:
        rec = MemoryRecord(
            id=entry["id"],
            content=entry["content"],
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
        )
        stored = b.add_memory(rec)
        id_map[entry["id"]] = stored.id
    return id_map


# ---------------------------------------------------------------------------
# Golden retrieval tests
# ---------------------------------------------------------------------------


def test_golden_retrieval_recall_at_k(backend: BackendHandle) -> None:
    """
    recall@5 over 11 golden queries must be >= 0.70.

    Each golden case: (query, needle_id) where the needle is expected to
    appear in the top-5 search results.  The corpus is 70 memories with
    isolated cluster vocabularies; each needle shares >=4 distinctive tokens
    with its query, making it dominant under BM25 + HashingEmbedder fusion.

    Phase 2 exit criterion: this test must also pass on PostgresBackend
    (tsvector + pg_trgm + pgvector) with the same K and threshold, verifying
    that FTS ranking parity is within the bounded drift documented in
    design.md §6.1.
    """
    b = backend.backend
    _build_corpus(b)

    hits = 0
    miss_details: list[str] = []

    for query, needle_id, description in GOLDEN_CASES:
        resp = b.search(SearchRequest(query=query, limit=TOP_K))
        found_ids = {m.id for m in resp.memories}
        if needle_id in found_ids:
            hits += 1
        else:
            rank_all = b.search(SearchRequest(query=query, limit=100))
            rank_list = [m.id for m in rank_all.memories]
            actual_rank = rank_list.index(needle_id) + 1 if needle_id in rank_list else -1
            miss_details.append(
                f"  MISS [{description}]: needle={needle_id!r} "
                f"not in top-{TOP_K} (actual rank={actual_rank})"
            )

    recall = hits / len(GOLDEN_CASES)
    detail_str = "\n".join(miss_details) if miss_details else "  (no misses)"
    assert recall >= RECALL_THRESHOLD, (
        f"Golden-set recall@{TOP_K} = {recall:.2f} < threshold {RECALL_THRESHOLD:.2f} "
        f"({hits}/{len(GOLDEN_CASES)} hits).\n"
        f"Misses:\n{detail_str}\n\n"
        f"If a backend change caused this regression, verify:\n"
        f"  1. The FTS tokenizer covers the golden query tokens.\n"
        f"  2. HashingEmbedder embeddings are stored correctly.\n"
        f"  3. RRF fusion is not dropping the needle's scores.\n"
        f"See design.md §6.1 for the bounded-drift rationale."
    )


def test_golden_corpus_all_memories_searchable(backend: BackendHandle) -> None:
    """Every corpus memory is retrievable by its first 4 words (sanity check)."""
    b = backend.backend
    _build_corpus(b)

    not_found: list[str] = []
    for entry in CORPUS:
        words = str(entry["content"]).split()[:4]
        query = " ".join(words)
        resp = b.search(SearchRequest(query=query, limit=TOP_K))
        if entry["id"] not in {m.id for m in resp.memories}:
            not_found.append(f"  {entry['id']!r}: query={query!r}")

    assert not not_found, (
        f"{len(not_found)} corpus memories not found in top-{TOP_K} for their own content:\n"
        + "\n".join(not_found)
    )


def test_golden_retrieval_total_found_consistent(backend: BackendHandle) -> None:
    """total_found equals len(resp.memories) — auto-included notes must not inflate it."""
    b = backend.backend
    _build_corpus(b)
    for query, _, description in GOLDEN_CASES:
        resp = b.search(SearchRequest(query=query, limit=TOP_K))
        assert resp.total_found == len(resp.memories), (
            f"[{description}] total_found={resp.total_found} != "
            f"len(memories)={len(resp.memories)} — "
            "auto-included notes must not count toward total_found"
        )
