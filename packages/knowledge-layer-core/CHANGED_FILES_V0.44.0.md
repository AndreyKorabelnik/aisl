# Changed files — knowledge-layer-core 0.44.0

- `knowledge_layer_core/value_flow.py` — evidence-based rename/transformation classification, typed static constants and deterministic derivation grouping.
- `knowledge_layer_core/suite_schema.py` — suite schema v12 and direct-edge derivation kind/source-count columns.
- `knowledge_layer_core/query.py` — derivation filters and result fields.
- `knowledge_layer_core/evidence.py` — derivation query parameters for the direct-flow evidence tool.
- `docs/REPOSITORY_DIRECT_VALUE_FLOW_V2.md` — canonical v2 semantics.
- `docs/REPOSITORY_DIRECT_VALUE_FLOW_V1.md` — removed; no legacy contract is retained.
- `tests/test_repository_value_flow.py` — rename, transformation, derivation grouping and static-constant regression cases.
- `validation/iteration-41-real-mapper-value-flow.json` — real core-to-KLC validation result.
- `README.md`, `pyproject.toml`, `knowledge_layer_core/version.py`, `tests/test_offline_validation.py` — release/version updates.
