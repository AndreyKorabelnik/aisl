# knowledge-layer-core 0.59.44 — Legacy Cleanup Block 6

Retires the obsolete KLC repository/workspace build bridge that still consumed the Core-produced `code_conceptual_model/v2` umbrella artifact.

Changes:
- removed the old `build_workspace_data_model` and `build_knowledge_layer` producer APIs;
- removed repository/selection/common-scope build modules used only by that retired path;
- removed `RepositoryEvidence`, `KnowledgeLayerBuildRequest`, and `KnowledgeLayerMaterializer`;
- removed obsolete build-request IO helpers and package exports;
- removed conceptual-model-specific ingestion loaders from the shared helper module;
- removed `legacy_code_conceptual_model_consumed=False`;
- removed the compatibility note that explicitly named the rejected legacy umbrella;
- kept the read/query layer and current typed materialization runtime unchanged;
- added negative tests proving the retired API/modules are absent and current KLC source has no `code_conceptual_model` dependency.

No adapter, dual-read, or umbrella-to-typed conversion path was added.
