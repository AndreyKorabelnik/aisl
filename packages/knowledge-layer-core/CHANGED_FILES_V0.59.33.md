# KLC 0.59.33 changed files

- `knowledge_layer_core/attribute_extension_context_schema.py` — typed `data-model-attribute-extension-context/v1` schema for agent-ready data-model extension knowledge.
- `knowledge_layer_core/attribute_extension_context_builder.py` — compose declared relationships, storage/key semantics, structural key correspondences, SQL anchors, and observed physical candidates without generating SQL.
- `knowledge_layer_core/key_expression_correspondence.py` — shared exact structural key-expression canonicalizer extracted from the existing workspace data-model correspondence mechanism.
- `knowledge_layer_core/workspace_data_model.py` — reuse the shared structural-expression canonicalizer; no separate matching algorithm.
- `knowledge_layer_core/materialization_contracts.py` — register `data-model-attribute-extension-context` materialization and capabilities.
- `knowledge_layer_core/materialization_runtime.py` — generic runtime handler for the new materialization.
- `tests/test_attribute_extension_context.py` — generic join-semantics tests and materialization contract coverage.
- `tests/test_materialization_contracts.py`, `tests/test_materialization_runtime.py` — migrate canonical materialization-count/registry expectations.
- `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.59.33.
- release/test/real-validation metadata for this checkpoint.
