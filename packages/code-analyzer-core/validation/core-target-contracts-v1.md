# Core Target Analysis Contracts v1

- Core version: `0.44.22`
- Schema: `core_target_analysis_contracts/v1`
- Execution effect: `none`
- Fingerprint: `764232c51fbe9a907fed15ace3079136f448c1aea6a64b62f664b16dc17ec114`

## Target boundary

- Foundation is a Core-owned immutable technical source index.
- Public Core analyzers produce independent typed evidence artifacts.
- KLC composes evidence into knowledge models.
- Runner records execution and lifecycle but does not define evidence semantics.
- Evidence meaning is selected by `artifact_kind + schema_version`, not by `task_id`.

## Current assessment

- Foundation stages now: **9**
- Foundation stages allowed by the target contract under current classification: **9**
- Foundation violations: **0**
- Observed internal stage dependencies: **6**
- Internal pipeline-state reads: **3**
- Knowledge materializations still inside Core: **0**
- Registered generic evidence analyzers: **11**
- Generic Core evidence runtime: `core_evidence_runtime/v1`

## Foundation transition

- No current Foundation violations detected.

## Internal analyzer implementation diagnostics

These are analyzer-internal stage/reuse diagnostics, not dependencies between public evidence analyzers.

- `declared_value_summary_scan` depends on `declared_value_scan_optional`.
- `java_data_model_lineage_build` depends on `java_persistence_lineage_build_optional`.
- `java_field_flow_build` depends on `java_structural_scan`.
- `java_system_interaction_enrichment` depends on `config_scan`, `java_structural_scan`.
- `java_table_observation_build` depends on `java_structural_scan`, `db_schema_scan`.
- `java_traceability_build` depends on `java_data_flow_build`.
- `java_field_flow_build` reads analyzer-owned pipeline state: `interfaces`, `schemas`.
- `java_system_interaction_enrichment` reads analyzer-owned pipeline state: `config_facts`, `schemas`, `interfaces`.
- `java_table_observation_build` reads analyzer-owned pipeline state: `facts filtered to jpa_entity and jpa_relationship`, `db_schema`.

## Knowledge materializations to remove from Core


## Next contract owners

- `knowledge_materialization_contract/v2` — **knowledge-layer-core**: Declare required and optional evidence artifact kinds and produced knowledge models.
- `analysis_execution_result_contract/v1` — **static-analysis-runner**: Record executed analyzers and produced evidence artifacts without assigning their subject semantics.
- `evidence_semantic_routing/v1` — **shared-boundary**: Evidence meaning is selected by artifact_kind plus schema_version; task_id may remain execution provenance only.
