# Changed files — knowledge-layer-core 0.61.0a37

- `knowledge_layer_core/repository_source_occurrences.py` — generic SourceOccurrence extraction/linkage from official evidence contracts.
- `knowledge_layer_core/repository_inventory_schema.py` — repository-inventory/v4 and normalized source occurrence/link tables.
- `knowledge_layer_core/repository_inventory_builder.py` — builds/publishes source occurrence graph and capability metadata.
- `knowledge_layer_core/materialization_contracts.py` — v4 output and source-occurrence capability.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version bump.
- `tests/test_repository_source_occurrences.py` — Java/SQL/structured provenance tests.
- `tests/test_repository_inventory_materialization.py`, `tests/test_materialization_contracts.py` — v4/materialization assertions.
- Block D extends the same files/tests with explicit coverage gap localization scope/status and diagnostic provenance pass-through.
