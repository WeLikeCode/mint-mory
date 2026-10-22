"""RED tests for task 1 — tenant types and errors in ``types.py``.

They trace the acceptance criteria of requirements 1.1–1.5: the tenant id
constants and validator, the ``Tenant`` model, the error classes, the
``tenant_id`` field on the five persisted models, and the request models that
must stay unchanged.
"""

from __future__ import annotations

from datetime import datetime

import mintmory.core.types as types
import pytest
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    CrossTenantLinkError,
    InvalidTenantIdError,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySummary,
    ProtectedTenantError,
    QueryResult,
    QuerySession,
    ScopeRequiredError,
    SearchRequest,
    TenancyNotSupportedError,
    TenantError,
    TenantImmutableError,
    TenantInactiveError,
    TenantMigrationError,
    TenantNotFoundError,
    validate_tenant_id,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Requirement 1.1 — constants and the single validator
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-0a1cfe6b")
def test_validate_tenant_id_returns_valid_ids_unchanged() -> None:
    for tenant_id in ("acme", "t-1", "a_b", "global"):
        assert validate_tenant_id(tenant_id) == tenant_id


@pytest.mark.l4("C-0a1cfe6b")
def test_validate_tenant_id_rejects_invalid_ids() -> None:
    for tenant_id in ("", "Acme", "-x", "a b", "a" * 129):
        try:
            validate_tenant_id(tenant_id)
        except InvalidTenantIdError as exc:
            assert str(exc) == (
                f"invalid tenant id {tenant_id!r}: expected ^[a-z0-9][a-z0-9_-]{{0,127}}$"
            )
        else:
            pytest.fail(f"validate_tenant_id accepted invalid id {tenant_id!r}")


@pytest.mark.l4("C-0a1cfe6b")
def test_tenant_constants_match_the_contract() -> None:
    assert getattr(types, "TENANT_GLOBAL", None) == "global"
    assert getattr(types, "TENANT_ID_PATTERN", None) == r"^[a-z0-9][a-z0-9_-]{0,127}$"
    assert validate_tenant_id("global") == "global"


# ---------------------------------------------------------------------------
# Requirement 1.2 — the Tenant model
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-edc43a92")
def test_tenant_model_defaults() -> None:
    tenant_cls = getattr(types, "Tenant", None)
    assert tenant_cls is not None, "types.Tenant is not defined"
    tenant = tenant_cls(id="acme")
    assert tenant.id == "acme"
    assert tenant.name == ""
    assert tenant.is_active is True
    assert isinstance(tenant.created_at, datetime)
    assert isinstance(tenant.updated_at, datetime)


@pytest.mark.l4("C-edc43a92")
def test_tenant_model_validates_id() -> None:
    tenant_cls = getattr(types, "Tenant", None)
    assert tenant_cls is not None, "types.Tenant is not defined"
    with pytest.raises(ValidationError):
        tenant_cls(id="Acme")


# ---------------------------------------------------------------------------
# Requirement 1.3 — the error classes
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ee05ebb1")
def test_tenant_not_found_error_message_and_attribute() -> None:
    exc = TenantNotFoundError("acme")
    assert isinstance(exc, TenantError)
    assert str(exc) == "tenant 'acme' not found"
    assert getattr(exc, "tenant_id", None) == "acme"


@pytest.mark.l4("C-ee05ebb1")
def test_tenant_inactive_error_message_and_attribute() -> None:
    exc = TenantInactiveError("acme")
    assert isinstance(exc, TenantError)
    assert str(exc) == "tenant 'acme' is inactive (read-only)"
    assert getattr(exc, "tenant_id", None) == "acme"


@pytest.mark.l4("C-ee05ebb1")
def test_protected_tenant_error_message() -> None:
    exc = ProtectedTenantError()
    assert isinstance(exc, TenantError)
    assert str(exc) == "the global tenant cannot be deactivated"


@pytest.mark.l4("C-ee05ebb1")
def test_invalid_tenant_id_error_message_and_attribute() -> None:
    exc = InvalidTenantIdError("Acme")
    assert isinstance(exc, TenantError)
    assert isinstance(exc, ValueError)
    assert str(exc) == "invalid tenant id 'Acme': expected ^[a-z0-9][a-z0-9_-]{0,127}$"
    assert getattr(exc, "tenant_id", None) == "Acme"


@pytest.mark.l4("C-ee05ebb1")
def test_cross_tenant_link_error_message_and_attributes() -> None:
    exc = CrossTenantLinkError("A", "T1", "B", "T2")
    assert isinstance(exc, TenantError)
    assert str(exc) == "cross-tenant reference: 'A' (tenant 'T1') -> 'B' (tenant 'T2')"
    assert getattr(exc, "first_id", None) == "A"
    assert getattr(exc, "first_tenant", None) == "T1"
    assert getattr(exc, "second_id", None) == "B"
    assert getattr(exc, "second_tenant", None) == "T2"


@pytest.mark.l4("C-ee05ebb1")
def test_tenant_immutable_error_message_and_attributes() -> None:
    exc = TenantImmutableError("M", "T1", "T2")
    assert isinstance(exc, TenantError)
    assert str(exc) == "memory 'M' belongs to tenant 'T1'; it cannot move to 'T2'"
    assert getattr(exc, "memory_id", None) == "M"
    assert getattr(exc, "stored_tenant", None) == "T1"
    assert getattr(exc, "requested_tenant", None) == "T2"


@pytest.mark.l4("C-ee05ebb1")
def test_scope_required_error_message_and_attributes() -> None:
    exc = ScopeRequiredError("dream", "acme")
    assert isinstance(exc, TenantError)
    assert str(exc) == "dream requires the global scope; this process is scoped to tenant 'acme'"
    assert getattr(exc, "operation", None) == "dream"
    assert getattr(exc, "scope", None) == "acme"


@pytest.mark.l4("C-ee05ebb1")
def test_tenant_migration_error_message_and_attribute() -> None:
    exc = TenantMigrationError("boom")
    assert isinstance(exc, TenantError)
    assert str(exc) == "tenant migration failed: boom; the existing tables were left unchanged"
    assert getattr(exc, "cause", None) == "boom"


@pytest.mark.l4("C-ee05ebb1")
def test_tenancy_not_supported_error_message_and_attribute() -> None:
    exc = TenancyNotSupportedError("get_summary")
    assert isinstance(exc, TenantError)
    assert isinstance(exc, NotImplementedError)
    assert str(exc) == "get_summary: tenancy on the Postgres backend is not available yet"
    assert getattr(exc, "operation", None) == "get_summary"


# ---------------------------------------------------------------------------
# Requirement 1.4 — tenant_id on the five persisted models
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-bdfc8484")
def test_memory_record_tenant_default_and_validation() -> None:
    assert "tenant_id" in MemoryRecord.model_fields
    record = MemoryRecord(content="x", category=MemoryCategory.FACT)
    assert getattr(record, "tenant_id", None) == "global"
    assert (
        getattr(
            MemoryRecord.model_validate({"content": "x", "category": "fact", "tenant_id": "t1"}),
            "tenant_id",
            None,
        )
        == "t1"
    )
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate({"content": "x", "category": "fact", "tenant_id": "Bad"})


@pytest.mark.l4("C-bdfc8484")
def test_concept_link_tenant_default_and_validation() -> None:
    assert "tenant_id" in ConceptLink.model_fields
    link = ConceptLink(
        source_memory_id="m1",
        target_memory_id="m2",
        link_type=ConceptLinkType.RELATES_TO,
    )
    assert getattr(link, "tenant_id", None) == "global"
    assert (
        getattr(
            ConceptLink.model_validate(
                {
                    "source_memory_id": "m1",
                    "target_memory_id": "m2",
                    "link_type": "relates_to",
                    "tenant_id": "t1",
                }
            ),
            "tenant_id",
            None,
        )
        == "t1"
    )
    with pytest.raises(ValidationError):
        ConceptLink.model_validate(
            {
                "source_memory_id": "m1",
                "target_memory_id": "m2",
                "link_type": "relates_to",
                "tenant_id": "Bad",
            }
        )


@pytest.mark.l4("C-bdfc8484")
def test_memory_summary_tenant_default_and_validation() -> None:
    assert "tenant_id" in MemorySummary.model_fields
    summary = MemorySummary(concept="acme", summary_text="s", memory_count=1)
    assert getattr(summary, "tenant_id", None) == "global"
    assert (
        getattr(
            MemorySummary.model_validate(
                {"concept": "acme", "summary_text": "s", "memory_count": 1, "tenant_id": "t1"}
            ),
            "tenant_id",
            None,
        )
        == "t1"
    )
    with pytest.raises(ValidationError):
        MemorySummary.model_validate(
            {"concept": "acme", "summary_text": "s", "memory_count": 1, "tenant_id": "Bad"}
        )


@pytest.mark.l4("C-bdfc8484")
def test_query_session_tenant_default_and_validation() -> None:
    assert "tenant_id" in QuerySession.model_fields
    session = QuerySession(query_text="q")
    assert getattr(session, "tenant_id", None) == "global"
    assert (
        getattr(
            QuerySession.model_validate({"query_text": "q", "tenant_id": "t1"}),
            "tenant_id",
            None,
        )
        == "t1"
    )
    with pytest.raises(ValidationError):
        QuerySession.model_validate({"query_text": "q", "tenant_id": "Bad"})


@pytest.mark.l4("C-bdfc8484")
def test_query_result_tenant_default_and_validation() -> None:
    assert "tenant_id" in QueryResult.model_fields
    result = QueryResult(session_id="s", memory_id="m", relevance_score=0.5)
    assert getattr(result, "tenant_id", None) == "global"
    assert (
        getattr(
            QueryResult.model_validate(
                {"session_id": "s", "memory_id": "m", "relevance_score": 0.5, "tenant_id": "t1"}
            ),
            "tenant_id",
            None,
        )
        == "t1"
    )
    with pytest.raises(ValidationError):
        QueryResult.model_validate(
            {"session_id": "s", "memory_id": "m", "relevance_score": 0.5, "tenant_id": "Bad"}
        )


# ---------------------------------------------------------------------------
# Requirement 1.5 — request models stay unchanged
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-59ef9e7c", "C-bdfc8484")
def test_core_request_models_keep_no_tenant_field() -> None:
    assert "tenant_id" not in SearchRequest.model_fields
    assert "tenant_id" not in MemoryFilter.model_fields
    assert "tenant_id" in MemoryRecord.model_fields


@pytest.mark.l4("C-59ef9e7c", "C-bdfc8484")
def test_http_request_bodies_gain_no_tenant_field() -> None:
    from mintmory.api.schemas import (
        CaptionRunRequest,
        ConceptLinkCreate,
        DreamRequest,
        ImageCaptionPut,
        MemoryCreate,
        MemoryUpdate,
        NoteCreate,
        SessionFeedback,
        SummaryPut,
    )

    for model in (
        MemoryCreate,
        MemoryUpdate,
        ConceptLinkCreate,
        NoteCreate,
        DreamRequest,
        SessionFeedback,
        SummaryPut,
        ImageCaptionPut,
        CaptionRunRequest,
    ):
        assert "tenant_id" not in model.model_fields, model.__name__
    assert "tenant_id" in MemoryRecord.model_fields
