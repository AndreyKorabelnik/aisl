# Knowledge Materialization Contracts v1

- KLC version: `0.53.8`
- Schema: `knowledge_materialization_catalog/v1`
- Execution effect: `none`
- Fingerprint: `90e410194ff16a8223a05a32a82d4128b48556b79c54a619539824c4baa34f1f`

## Target boundary

- Core publishes independent typed evidence artifacts.
- KLC materializations declare required and optional evidence kinds.
- Evidence meaning is selected by `artifact_kind + schema_version`.
- `task_id`, `suite_id` and `profile_id` remain execution provenance only.
- Capabilities are published from completed KLC materializations.

## Current assessment

- Current KLC materializations: **10**
- Planned Core → KLC materializations: **4**
- Current typed-input materializations: **2**
- Current task-semantic routes: **8**
- Contract compliant now: **no**

## Planned Core → KLC migration

| Priority | Core stage | Target KLC materialization | Readiness |
|---:|---|---|---|
| 1 | `code_conceptual_model_build` | `conceptual-data-model` | `evidence_sufficiency_and_parity_required` |
| 2 | `system_description_enrichment` | `system-description` | `query_ingestion_exists_derivation_contract_missing` |
| 3 | `reference_data_fact_base` | `reference-data` | `queries_exist_minimum_evidence_contract_missing` |
| 4 | `workspace_sql_mart_catalog_build` | `workspace-sql-mart-catalog` | `repository_sql_contract_exists_runner_workflow_boundary_missing` |

## Current task-semantic debt

### `suite.query-artifact-import`

- Source: `knowledge_layer_core.suite_builder.QUERY_ARTIFACTS`
- Current selector: `task_id`
- Task IDs: `system-description`, `reference-data`, `flow-lineage`, `interaction-lineage`, `persistence-lineage`
- Target selector: `artifact_kind_plus_schema_version`
- Transition: `replace_task_keyed_artifact_name_tables_with_typed_evidence_importers`

### `suite.flow-catalog-import`

- Source: `knowledge_layer_core.suite_builder._register_all_task_artifacts`
- Current selector: `task_id`
- Task IDs: `flow-lineage`, `interaction-lineage`
- Target selector: `value-flow-evidence schema`
- Transition: `import_flow_catalog_from_typed_evidence_manifest`

### `suite.reference-detail-import`

- Source: `knowledge_layer_core.suite_builder._ingest_reference_detail_records`
- Current selector: `task_id`
- Task IDs: `reference-data`
- Target selector: `declared-value-evidence and literal-write-evidence schemas`
- Transition: `replace_reference_task_directory_scan_with_typed_import`

### `suite.common-data-model-selection`

- Source: `knowledge_layer_core.suite_builder._data_model_repositories`
- Current selector: `task_id`
- Task IDs: `data-model`
- Target selector: `required evidence kinds for conceptual-data-model`
- Transition: `select_repository_evidence_by_artifact_contract_not_task`

### `suite.capability-publication`

- Source: `knowledge_layer_core.suite_builder._suite_capabilities`
- Current selector: `task_id`
- Task IDs: `system-description`, `data-model`, `reference-data`, `flow-lineage`, `interaction-lineage`, `persistence-lineage`, `system-interaction`, `conceptual-data-model`, `sql-mart`, `git-change-complexity`
- Target selector: `successfully materialized KLC model capability`
- Transition: `publish_capabilities_from_materialization_results_not_requested_tasks`

### `portfolio.topology-task-selection`

- Source: `knowledge_layer_core.topology_builder.build_portfolio_topology`
- Current selector: `task_id`
- Task IDs: `portfolio-topology`
- Target selector: `repository-interface-catalog-evidence schema`
- Transition: `select_topology_inputs_by_typed_artifact_contract`

### `query.default-task-filters`

- Source: `knowledge_layer_core.query.KnowledgeLayerQuery`
- Current selector: `task_id default filters`
- Task IDs: `system-description`, `reference-data`, `flow-lineage`, `persistence-lineage`
- Target selector: `materialized model/table kind`
- Transition: `query_typed_KLC_models_without_task_semantic_defaults`

### `reporting.system-description-task-filter`

- Source: `knowledge_layer_core.reporting_queries.ReportingQueryService`
- Current selector: `task_id`
- Task IDs: `system-description`
- Target selector: `system-description materialization outputs`
- Transition: `query_KLC_owned_system_description_model`

## Materialization contracts

### Current

#### `common-data-model`

- Lifecycle: `current_boundary_migration_required`
- Scope: `repository_or_workspace`
- Required evidence: `java-structure-evidence`, `java-persistence-evidence`, `java-mapping-evidence`, `physical-schema-evidence`
- Optional evidence: `source-observation-evidence`, `declared-value-evidence`, `configuration-evidence`
- Produced models: `knowledge_layer_data_model_core/v1`, `workspace_data_model/v16`

#### `physical-model`

- Lifecycle: `current_typed_input`
- Scope: `physical_model_source`
- Required evidence: `physical-model`
- Optional evidence: —
- Produced models: `knowledge_layer_physical_model/v1`

#### `sql-analysis`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_sql_source`
- Required evidence: `sql-analysis`
- Optional evidence: `physical-model`
- Produced models: `knowledge_layer_sql/v2`

#### `suite-evidence-registry`

- Lifecycle: `current_task_semantics_removal_required`
- Scope: `suite`
- Required evidence: `analysis-execution-result`
- Optional evidence: `core-foundation`
- Produced models: `knowledge_layer_suite_scope/v17`

#### `system-interactions`

- Lifecycle: `current_partial_evidence_contract`
- Scope: `workspace`
- Required evidence: `interaction-boundary-evidence`
- Optional evidence: `configuration-evidence`, `execution-context-evidence`
- Produced models: `workspace_system_interaction/v5`

#### `interaction-coverage`

- Lifecycle: `current`
- Scope: `workspace`
- Required evidence: `interaction-boundary-evidence`
- Optional evidence: —
- Produced models: `repository_interaction_coverage/v1`

#### `interaction-islands`

- Lifecycle: `current`
- Scope: `workspace_or_portfolio`
- Required evidence: `repository-interaction-evidence`
- Optional evidence: `interaction-coverage`
- Produced models: `repository_interaction_island/v2`

#### `interaction-field-contracts`

- Lifecycle: `current`
- Scope: `workspace`
- Required evidence: `repository-value-flow`, `repository-interaction-evidence`
- Optional evidence: —
- Produced models: `workspace_system_interaction_field_contract/v2`

#### `repository-value-flow`

- Lifecycle: `current_task_semantics_removal_required`
- Scope: `workspace`
- Required evidence: `value-flow-evidence`
- Optional evidence: `persistence-evidence`, `interaction-boundary-evidence`
- Produced models: `repository_value_flow/v6`, `repository_attribute_path/v2`

#### `portfolio-topology`

- Lifecycle: `current_profile_task_coupled`
- Scope: `portfolio`
- Required evidence: `repository-interface-catalog-evidence`
- Optional evidence: `repository-metadata`
- Produced models: `portfolio_topology/v1`, `portfolio_interaction_islands/v1`

### Planned Core → KLC

#### `conceptual-data-model`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `java-structure-evidence`, `java-persistence-evidence`, `java-mapping-evidence`
- Optional evidence: `physical-schema-evidence`, `table-observation-evidence`, `declared-value-evidence`
- Produced models: `conceptual-data-model/v1`, `logical-physical-model-mapping/v1`, `effective-data-model/v1`

#### `system-description`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `interaction-boundary-evidence`, `configuration-evidence`, `build-dependency-evidence`, `storage-access-evidence`
- Optional evidence: `value-flow-evidence`, `physical-schema-evidence`
- Produced models: `system-description/v1`, `system-scenario/v1`, `storage-usage-summary/v1`

#### `reference-data`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `declared-value-evidence`, `literal-write-evidence`
- Optional evidence: `java-persistence-evidence`, `value-flow-evidence`, `interaction-boundary-evidence`, `configuration-evidence`
- Produced models: `reference-data-fact-base/v1`, `declared-value-set/v1`, `reference-data-candidate-view/v1`

#### `workspace-sql-mart-catalog`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `workspace`
- Required evidence: `sql-analysis`
- Optional evidence: `physical-model`, `repository-metadata`
- Produced models: `workspace-sql-mart-catalog/v1`, `workspace-sql-source-inventory/v1`

## Blocking contracts

- analysis_execution_result_contract/v1 owned by static-analysis-runner
- typed Core evidence artifact schemas referenced by planned materializations
- conceptual_model_evidence_sufficiency/v1 before first migration

## Next steps

- Publish analysis_execution_result_contract/v1 in Runner.
- Define typed evidence schemas required by conceptual-data-model.
- Build conceptual_model_evidence_sufficiency/v1 from the current Core materializer.
- Replace task_id-based KLC import meaning with evidence artifact routing before switching the first materialization.
