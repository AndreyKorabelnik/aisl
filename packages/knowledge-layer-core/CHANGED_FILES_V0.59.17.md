# Changed files — 0.59.17

- `knowledge_layer_core/sql_analysis_schema.py` — workflow target lineage/gap derived tables and indexes.
- `knowledge_layer_core/sql_workflow_target_lineage.py` — materialization from observed workflow target, contextual script invocation, projections and CTE/derived column flow.
- `knowledge_layer_core/sql_analysis_builder.py` — executes workflow target lineage materialization and records validation summary.
- `knowledge_layer_core/query.py` — exposes workflow-resolved lineage through the existing target-column-lineage / field-calculation query surface.
- `tests/test_sql_analysis_knowledge_layer.py` — regression for workflow-only targets and existing direct lineage behavior.
- version metadata — 0.59.17.
