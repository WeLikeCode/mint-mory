"""RED tests for task 7 — OpenAPI response schemas (R7.2).

Only the four response schemas ``MemoryRecord``, ``ConceptLink``,
``MemorySummary`` and ``QuerySession`` gain ``tenant_id``.  No ``Tenant`` schema,
path, header or request-body field is added: the HTTP API accepts no tenant
input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

SPEC_PATH = Path(__file__).resolve().parents[3] / "docs" / "openapi" / "mintmory.yaml"
RESPONSE_SCHEMAS = ("MemoryRecord", "ConceptLink", "MemorySummary", "QuerySession")


def _spec() -> dict[str, Any]:
    loaded = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _schemas() -> dict[str, Any]:
    schemas = _spec()["components"]["schemas"]
    assert isinstance(schemas, dict)
    return cast("dict[str, Any]", schemas)


@pytest.mark.l4("C-58364fba")
def test_openapi_response_schemas_declare_tenant_id() -> None:
    schemas = _schemas()

    for name in RESPONSE_SCHEMAS:
        properties = schemas.get(name, {}).get("properties", {})
        tenant = properties.get("tenant_id")
        assert tenant is not None, f"{name}.tenant_id is missing from the OpenAPI spec"
        assert tenant["type"] == "string", name
        assert tenant["default"] == "global", name
        description = tenant["description"]
        assert "^[a-z0-9][a-z0-9_-]{0,127}$" in description, name


@pytest.mark.l4("C-58364fba")
def test_openapi_tenant_id_is_only_on_the_four_response_schemas() -> None:
    spec = _spec()
    schemas = _schemas()

    with_tenant = sorted(
        name
        for name, schema in schemas.items()
        if isinstance(schema, dict) and "tenant_id" in schema.get("properties", {})
    )
    assert with_tenant == sorted(RESPONSE_SCHEMAS)
    assert "Tenant" not in schemas

    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                if not isinstance(parameter, dict):
                    continue
                assert "tenant" not in str(parameter.get("name", "")).lower()
