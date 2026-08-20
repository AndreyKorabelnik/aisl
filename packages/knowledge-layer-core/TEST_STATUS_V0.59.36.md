# Test status — knowledge-layer-core 0.59.36

- Targeted query/builder regression: 16 passed.
- `python -m compileall -q knowledge_layer_core`: passed.
- Real prepared-artifact smoke: passed against the existing `code-declared-data-model/v1` DuckDB from the data-model attribute-extension Gold run; Russian documentation search and exact `Individual` detail returned source refs/provenance without JOIN inference.
- No Core/Runner/KLC production rerun was used for the read-surface smoke.
