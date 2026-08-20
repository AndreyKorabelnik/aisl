from pathlib import Path
import os
import pytest

from prepared_knowledge_runtime import DataModelQueryService


def test_bulk_fields_matches_object_field_counts() -> None:
    value = os.environ.get("UCP_DATA_MODEL_KNOWLEDGE_LAYER")
    if not value:
        pytest.skip("UCP_DATA_MODEL_KNOWLEDGE_LAYER is not configured")
    service = DataModelQueryService(Path(value))
    inventory = service.search_objects(max_results=5000)
    bulk = service.list_fields()
    by_object: dict[str, int] = {}
    for item in bulk.items:
        by_object[str(item.get("object_id") or "")] = by_object.get(str(item.get("object_id") or ""), 0) + 1
    for object_item in inventory.items[:25]:
        object_id = str(object_item["object_id"])
        detail = service.get_fields(object_id)
        assert by_object.get(object_id, 0) == len(detail.items)


def test_generic_workspace_uses_workspace_query_surface() -> None:
    value = os.environ.get("UCP_GENERIC_KNOWLEDGE_LAYER")
    if not value:
        pytest.skip("UCP_GENERIC_KNOWLEDGE_LAYER is not configured")
    service = DataModelQueryService(Path(value))
    result = service.list_fields()
    assert result.summary["field_count"] > 0
    relationships = service.get_relationships()
    assert relationships.summary["relationship_count"] == 0
