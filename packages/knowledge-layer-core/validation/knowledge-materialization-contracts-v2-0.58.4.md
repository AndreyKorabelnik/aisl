# Knowledge Materialization Contracts v2

- KLC version: `0.58.4`
- Schema: `knowledge_materialization_catalog/v2`
- Execution effect: `read_only_contract_catalog`
- Fingerprint: `07b9c21b980306f0f7081d42fa6acbf037e49b5cebe03dc2a62c1abceed3f957`

## Target boundary

- Core publishes independent typed evidence artifacts.
- KLC materializations declare required and optional evidence kinds.
- Evidence meaning is selected by `artifact_kind + schema_version`.
- `task_id`, `suite_id` and `profile_id` remain execution provenance only.
- Capabilities are published from completed KLC materializations.

## Current assessment

- Current KLC materializations: **16**
- Planned Core → KLC materializations: **0**
- Current typed-input materializations: **10**
- Current task-semantic routes: **5**
- Contract compliant now: **no**

## Planned Core → KLC migration

| Priority | Core stage | Target KLC materialization | Readiness |
|---:|---|---|---|

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
- Task IDs: `flow-lineage`, `persistence-lineage`
- Target selector: `artifact_kind_plus_schema_version`
- Transition: `replace_task_keyed_artifact_name_tables_with_typed_evidence_importers`

### `suite.flow-catalog-import`

- Source: `knowledge_layer_core.suite_builder._register_all_task_artifacts`
- Current selector: `task_id`
- Task IDs: `flow-lineage`
- Target selector: `value-flow-evidence schema`
- Transition: `import_flow_catalog_from_typed_evidence_manifest`

### `suite.capability-publication`

- Source: `knowledge_layer_core.suite_builder._suite_capabilities`
- Current selector: `task_id`
- Task IDs: `flow-lineage`, `persistence-lineage`, `system-interaction`, `conceptual-data-model`, `sql-mart`, `git-change-complexity`
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
- Task IDs: `flow-lineage`, `persistence-lineage`
- Target selector: `materialized model/table kind`
- Transition: `query_typed_KLC_models_without_task_semantic_defaults`

## Materialization contracts

### Current

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

#### `workspace-sql-catalog`

- Lifecycle: `current_typed_composition`
- Scope: `workspace`
- Required evidence: —
- Optional evidence: —
- Required KLC models: `sql-observed-data-usage` from `sql-analysis`
- Optional KLC models: —
- Produced models: `workspace-sql-catalog/v1`

#### `system-description`

- Lifecycle: `current_typed_input`
- Scope: `repository`
- Required evidence: `system-description-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `system-description/v1`

#### `reference-data`

- Lifecycle: `current_typed_input`
- Scope: `repository`
- Required evidence: `reference-data-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `reference-data/v1`

#### `suite-evidence-registry`

- Lifecycle: `current_task_semantics_removal_required`
- Scope: `suite`
- Required evidence: `analysis-execution-result`
- Optional evidence: `core-foundation`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `knowledge_layer_suite_scope/v17`

#### `system-interactions`

- Lifecycle: `current_typed_input`
- Scope: `workspace`
- Required evidence: `interaction-boundary-evidence`
- Optional evidence: `configuration-evidence`, `execution-context-evidence`
- Required KLC models: —
- Optional KLC models: —
- Produced models: `workspace_system_interaction/v6`

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

#### `logical-physical-mapping`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_workspace`
- Required evidence: `java-persistence-mapping-evidence`
- Optional evidence: —
- Required KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`
- Optional KLC models: —
- Produced models: `logical-physical-model-mapping/v1`

#### `code-declared-data-model`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_workspace`
- Required evidence: `java-type-structure-evidence`
- Optional evidence: —
- Required KLC models: —
- Optional KLC models: —
- Produced models: `code-declared-data-model/v1`

#### `effective-data-model`

- Lifecycle: `current_typed_klc_composition`
- Scope: `repository_or_workspace`
- Required evidence: —
- Optional evidence: —
- Required KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`, `logical-physical-model-mapping` from `logical-physical-mapping`
- Optional KLC models: `sql-observed-data-usage` from `sql-analysis`, `observed-storage-usage` from `observed-storage-usage`
- Produced models: `effective-data-model/v1`, `model-domain-cluster-view/v1`

#### `observed-storage-usage`

- Lifecycle: `current_typed_input`
- Scope: `repository_or_workspace`
- Required evidence: `storage-usage-evidence`
- Optional evidence: `model-evidence-gap`
- Required KLC models: —
- Optional KLC models: `code-declared-data-model` from `code-declared-data-model`, `physical-data-model` from `physical-model`
- Produced models: `observed-storage-usage/v1`

### Planned Core → KLC

## Blocking contracts


## Next steps

- Migrate remaining interaction, value-flow and topology routes from task semantics to typed evidence and materialization dependencies.
- Remove Task/Suite query and provenance surfaces after their remaining typed migrations are complete.
- Use typed artifact and KLC model routing for every new runtime materialization; legacy semantic routing is not supported.
