from __future__ import annotations

import inspect

import knowledge_layer_core
import prepared_knowledge_runtime
from knowledge_layer_core import data_model_schema


def test_removed_compatibility_schema_alias_is_not_public_contract() -> None:
    assert not hasattr(data_model_schema, "COMPATIBILITY_SCHEMA_VERSION")
    assert not hasattr(prepared_knowledge_runtime, "COMPATIBILITY_SCHEMA_VERSION")
    assert "COMPATIBILITY_SCHEMA_VERSION" not in prepared_knowledge_runtime.__all__




def test_active_sources_do_not_publish_removed_legacy_validation_tombstones() -> None:
    modules = [
        __import__("knowledge_layer_core.effective_data_model_builder", fromlist=["x"]),
        __import__("knowledge_layer_core.logical_physical_mapping_builder", fromlist=["x"]),
    ]
    text = "\n".join(inspect.getsource(module) for module in modules)
    assert "legacy_conceptual_model_consumed" not in text
    assert "legacy_fallback_used" not in text
