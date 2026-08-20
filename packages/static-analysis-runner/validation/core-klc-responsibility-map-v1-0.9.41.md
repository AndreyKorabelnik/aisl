# Core → KLC responsibility map

Schema: `core_klc_responsibility_map/v1`  
Execution effect: `none`

## Target architecture

- **Core Analyzer:** technical Foundation and independent source-grounded evidence analyzers.
- **Knowledge Layer:** composition of persisted evidence into knowledge models and views.
- **Runner:** process orchestration, retries and lifecycle only.

## Summary

- Core stages reviewed: **48**
- Produced result families: **67**
- Current Foundation stages: **10**
- Target Foundation/source-index stages: **9**
- Independent evidence analyzer stages: **30**
- Knowledge materializations to move to KLC: **4**
- Technical packaging stages: **5**

## Migration sequence

1. `code_conceptual_model_build` → knowledge-layer common/workspace data-model materialization (`partial_existing_klc_consumer`)
2. `system_description_enrichment` → knowledge-layer system-description materialization (`partial_query_record_ingestion_exists`)
3. `reference_data_fact_base` → knowledge-layer reference-data materialization (`partial_reference_queries_exist`)
4. `workspace_sql_mart_catalog_build` → knowledge-layer workspace SQL mart catalog materialization (`target_owner_clear_runtime_boundary_incomplete`)

## Knowledge materialization candidates

### `code_conceptual_model_build`

- Current owner: `code-analyzer-core`
- Target owner: `knowledge-layer-core`
- Affected profiles: `repository-data-model-static`, `repository-reference-data`, `repository-system-data-model`
- Affected tasks: `data-model`, `reference-data`
- Affected suites: `data-model`, `default-system-analysis`, `full-system-analysis`
- What stays in Core:
  - java structural evidence
  - persistence mapping evidence
  - mapping and relationship observations
  - physical schema evidence
  - source provenance and gaps
- What moves to KLC:
  - conceptual entities and fields projection
  - effective associations and inheritance composition
  - logical-to-physical model composition
- Evidence gaps / blockers:
  - KLC currently requires compact/code_conceptual_model artifacts from Core for repository data-model materialization.
  - The raw evidence families used by the current Core materializer must be enumerated and proven sufficient before removing that artifact.
  - Result parity must be checked on real repositories before the Core materializer is deleted.

### `reference_data_fact_base`

- Current owner: `code-analyzer-core`
- Target owner: `knowledge-layer-core`
- Affected profiles: `repository-reference-data`
- Affected tasks: `reference-data`
- Affected suites: `full-system-analysis`
- What stays in Core:
  - declared value evidence
  - literal write observations
  - storage and lineage evidence
  - interface and configuration evidence
  - source provenance and gaps
- What moves to KLC:
  - reference-data fact base
  - declared value set composition
  - reference-data candidate views and summaries
- Evidence gaps / blockers:
  - KLC currently imports Core-produced declared-value summaries and reference-data detail records.
  - The minimum evidence required to rebuild each reference_data_fact_base section in KLC must be fixed.
  - Candidate grouping must preserve facts-only semantics and unresolved alternatives.

### `system_description_enrichment`

- Current owner: `code-analyzer-core`
- Target owner: `knowledge-layer-core`
- Affected profiles: `repository-system-description`
- Affected tasks: `system-description`
- Affected suites: `default-system-analysis`, `full-system-analysis`
- What stays in Core:
  - interface boundary evidence
  - configuration and dependency evidence
  - storage access observations
  - source provenance and gaps
- What moves to KLC:
  - system scenarios
  - storage usage summaries
  - external dependency views
  - access-boundary and data-source views
- Evidence gaps / blockers:
  - KLC currently imports ready-made system-description compact artifacts selected by task_id.
  - Each view must be reconstructed from persisted evidence rather than copied from Core output.
  - Scenario and summary derivation rules are not yet expressed as KLC-owned materialization contracts.

### `workspace_sql_mart_catalog_build`

- Current owner: `code-analyzer-core`
- Target owner: `knowledge-layer-core`
- Affected profiles: `git-change-sql-spark-complexity-assessment`, `sql-mart-lineage`
- Affected tasks: none
- Affected suites: none
- What stays in Core:
  - repository SQL statements, scopes, relations, fields and lineage observations
  - repository-level SQL diagnostics and provenance
- What moves to KLC:
  - workspace aggregation of repository SQL marts
  - cross-repository SQL inventory and catalog views
- Evidence gaps / blockers:
  - The current Core catalog marks this as a declarative stage label over a fixed SQL runtime rather than an independently executed stage.
  - Repository SQL evidence contracts must be the only input to the KLC workspace materializer.
  - The owning Runner workflow and downstream API/report consumers must be identified before removing the label.

## Deferred work

- Redesigning Task and Suite boundaries.
- Eliminating repeated heavy analyzers.
- Caching and persisted evidence bundles.
- Runtime enforcement of analyzer independence.
