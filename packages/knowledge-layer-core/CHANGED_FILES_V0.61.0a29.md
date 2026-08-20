# Changed files — Knowledge Layer Core 0.61.0a29

- `knowledge_layer_core/code_declared_model_builder.py` — publishes product-level coverage aggregated losslessly from existing Core repository coverage and model gaps.
- `knowledge_layer_core/logical_physical_mapping_builder.py` — separates analysis completion from mapping outcome coverage; zero observed mappings now publish `no_mapping_evidence`, not generic `complete`.
- `knowledge_layer_core/physical_model_builder.py` — publishes parser-contract analysis coverage with typed counts and an explicit non-claim of business semantic completeness.
- tests for all three product coverage contracts.
- version metadata — 0.61.0a29.
