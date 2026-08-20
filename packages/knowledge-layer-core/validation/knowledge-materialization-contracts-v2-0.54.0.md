# Knowledge Materialization Contracts v2

- KLC version: `0.54.0`
- Schema: `knowledge_materialization_catalog/v2`
- Execution effect: `none`
- Fingerprint: `62cddf9f4cb76870144b247441724e3a6cdd0c3a3f460befcf5c61de255cead4`

## Target boundary

- Core publishes independent typed evidence artifacts.
- KLC materializations declare required and optional evidence kinds.
- Evidence meaning is selected by `artifact_kind + schema_version`.
- `task_id`, `suite_id` and `profile_id` remain execution provenance only.
- Capabilities are published from completed KLC materializations.

## Current assessment

- Current KLC materializations: **11**
- Planned Core → KLC materializations: **6**
- Current typed-input materializations: **3**
- Current task-semantic routes: **7**
- Contract compliant now: **no**

## Planned Core → KLC migration

| Priority | Core stage | Target KLC materialization | Readiness |
|---:|---|---|---|
| 2 | `code_conceptual_model_build` | `logical-physical-mapping` | `typed_persistence_mapping_contract_required` |
| 3 | `code_conceptual_model_build` | `observed-storage-usage` | `typed_storage_usage_contract_required` |
| 4 | `code_conceptual_model_build` | `effective-data-model` | `depends_on_independent_lower_level_materializations` |
| 5 | `system_description_enrichment` | `system-description` | `query_ingestion_exists_derivation_contract_missing` |
| 6 | `reference_data_fact_base` | `reference-data` | `queries_exist_minimum_evidence_contract_missing` |
| 7 | `workspace_sql_mart_catalog_build` | `workspace-sql-mart-catalog` | `repository_sql_contract_exists_runner_workflow_boundary_missing` |

## Legacy `code_conceptual_model/v2` decomposition

- Source artifact: `code_conceptual_model` / `code_conceptual_model/v2`
- Status: `legacy_umbrella_to_be_removed_after_scoped_parity`

| Legacy section | Route | Target materializations |
|---|---|---|
| `entities` | `split_by_semantics` | `code-declared-data-model`, `physical-model`, `effective-data-model` |
| `associations` | `split_by_semantics` | `code-declared-data-model`, `physical-model`, `logical-physical-mapping`, `sql-analysis`, `effective-data-model` |
| `generalizations` | `split_by_semantics` | `code-declared-data-model`, `logical-physical-mapping` |
| `physical_assets` | `direct` | `physical-model` |
| `physical_to_entity_mappings` | `direct` | `logical-physical-mapping` |
| `domains` | `derived_composite` | `effective-data-model` |
| `entity_clusters` | `derived_composite` | `effective-data-model` |
| `coverage_summary` | `distributed_metadata` | `code-declared-data-model`, `physical-model`, `logical-physical-mapping`, `observed-storage-usage`, `effective-data-model` |
| `evidence_gaps` | `distributed_metadata` | `code-declared-data-model`, `physical-model`, `logical-physical-mapping`, `observed-storage-usage`, `effective-data-model` |
| `provenance` | `distributed_metadata` | `code-declared-data-model`, `physical-model`, `logical-physical-mapping`, `observed-storage-usage`, `effective-data-model` |
| `sql_query_models` | `different_knowledge` | `sql-analysis` |
| `storage_operations` | `different_knowledge` | `observed-storage-usage`, `repository-value-flow` |
| `operations` | `different_knowledge` | `observed-storage-usage`, `repository-value-flow`, `system-description` |
| `interfaces` | `different_knowledge` | `system-interactions`, `system-description` |
| `access_boundaries` | `different_knowledge` | `system-interactions`, `system-description` |
| `scenarios` | `different_knowledge` | `system-description` |
| `scenario_storage_touches` | `different_knowledge` | `system-description`, `observed-storage-usage` |
| `data_flows` | `different_knowledge` | `repository-value-flow` |
| `field_flows` | `different_knowledge` | `repository-value-flow` |
| `stored_field_to_response_field_mappings` | `different_knowledge` | `repository-value-flow` |
| `attribute_mappings` | `different_knowledge` | `repository-value-flow` |
| `attribute_derivations` | `different_knowledge` | `repository-value-flow` |
| `data_dictionary` | `different_knowledge` | `reference-data` |
| `declared_value_sets` | `different_knowledge` | `reference-data` |
| `external_dependencies` | `different_knowledge` | `system-description` |
| `physical_asset_facts` | `evidence_detail` | `physical-model` |
| `source_inspection_requests` | `diagnostic_only` | — |

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

### `suite.capability-publication`

- Source: `knowledge_layer_core.suite_builder._suite_capabilities`
- Current selector: `task_id`
- Task IDs: `system-description`, `reference-data`, `flow-lineage`, `interaction-lineage`, `persistence-lineage`, `system-interaction`, `conceptual-data-model`, `sql-mart`, `git-change-complexity`
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

- Lifecycle: `retired_legacy_umbrella`
- Scope: `repository_or_workspace`
- Required evidence: `java-structure-evidence`, `java-persistence-evidence`, `java-mapping-evidence`, `physical-schema-evidence`
- Optional evidence: `source-observation-evidence`, `declared-value-evidence`, `configuration-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `knowledge_layer_data_model_core/v1`, `workspace_data_model/v16`

#### `physical-model`

- Lifecycle: `current_typed_input`
- Scope: `physical_model_source`
- Required evidence: `physical-model`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `knowledge_layer_physical_model/v1`

#### `sql-analysis`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_sql_source`
- Required evidence: `sql-analysis`
- Optional evidence: `physical-model`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `knowledge_layer_sql/v2`

#### `suite-evidence-registry`

- Lifecycle: `current_task_semantics_removal_required`
- Scope: `suite`
- Required evidence: `analysis-execution-result`
- Optional evidence: `core-foundation`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `knowledge_layer_suite_scope/v17`

#### `system-interactions`

- Lifecycle: `current_partial_evidence_contract`
- Scope: `workspace`
- Required evidence: `interaction-boundary-evidence`
- Optional evidence: `configuration-evidence`, `execution-context-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `workspace_system_interaction/v5`

#### `interaction-coverage`

- Lifecycle: `current`
- Scope: `workspace`
- Required evidence: `interaction-boundary-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `repository_interaction_coverage/v1`

#### `interaction-islands`

- Lifecycle: `current`
- Scope: `workspace_or_portfolio`
- Required evidence: `repository-interaction-evidence`
- Optional evidence: `interaction-coverage`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `repository_interaction_island/v2`

#### `interaction-field-contracts`

- Lifecycle: `current`
- Scope: `workspace`
- Required evidence: `repository-value-flow`, `repository-interaction-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `workspace_system_interaction_field_contract/v2`

#### `repository-value-flow`

- Lifecycle: `current_task_semantics_removal_required`
- Scope: `workspace`
- Required evidence: `value-flow-evidence`
- Optional evidence: `persistence-evidence`, `interaction-boundary-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `repository_value_flow/v6`, `repository_attribute_path/v2`

#### `portfolio-topology`

- Lifecycle: `current_profile_task_coupled`
- Scope: `portfolio`
- Required evidence: `repository-interface-catalog-evidence`
- Optional evidence: `repository-metadata`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `portfolio_topology/v1`, `portfolio_interaction_islands/v1`

#### `code-declared-data-model`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_workspace`
- Required evidence: `java-type-structure-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `code-declared-data-model/v1`

### Planned Core → KLC

#### `logical-physical-mapping`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `java-persistence-mapping-evidence`
- Optional evidence: `storage-usage-evidence`, `model-evidence-gap`
- Required KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`
- Optional KLC models: —
- Produced models: `logical-physical-model-mapping/v1`

#### `observed-storage-usage`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `storage-usage-evidence`
- Optional evidence: `model-evidence-gap`
- Required KLC models: —
- Optional KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`
- Produced models: `observed-storage-usage/v1`

#### `effective-data-model`

- Lifecycle: `planned_klc_composite_materialization`
- Scope: `repository_or_workspace`
- Required evidence: —
- Optional evidence: —
- Required KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`, `logical-physical-model-mapping` from `logical-physical-mapping`
- Optional KLC models: `sql-observed-data-usage` from `sql-analysis`, `observed-storage-usage` from `observed-storage-usage`
- Produced models: `effective-data-model/v1`, `model-domain-cluster-view/v1`

#### `system-description`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `interaction-boundary-evidence`, `configuration-evidence`, `build-dependency-evidence`, `storage-access-evidence`
- Optional evidence: `value-flow-evidence`, `physical-schema-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `system-description/v1`, `system-scenario/v1`, `storage-usage-summary/v1`

#### `reference-data`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `repository_or_workspace`
- Required evidence: `declared-value-evidence`, `literal-write-evidence`
- Optional evidence: `java-persistence-evidence`, `value-flow-evidence`, `interaction-boundary-evidence`, `configuration-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `reference-data-fact-base/v1`, `declared-value-set/v1`, `reference-data-candidate-view/v1`

#### `workspace-sql-mart-catalog`

- Lifecycle: `planned_core_to_klc_migration`
- Scope: `workspace`
- Required evidence: `sql-analysis`
- Optional evidence: `physical-model`, `repository-metadata`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `workspace-sql-mart-catalog/v1`, `workspace-sql-source-inventory/v1`

## Blocking contracts

- analysis_execution_result_contract/v1 owned by static-analysis-runner
- typed Core evidence artifact schemas referenced by planned materializations
- generic knowledge architecture audit owned by Runner before each migration

## Next steps

- Publish analysis_execution_result_contract/v1 in Runner.
- Update the user knowledge catalog and resolver to the decomposed data-model knowledge types.
- Build one generic Runner-owned knowledge architecture audit instead of one command per knowledge type.
- Use the current typed code-declared-data-model materialization as the first completed vertical knowledge path.
- Use typed artifact and KLC model routing for every new runtime materialization; legacy code-declared routing is removed.
