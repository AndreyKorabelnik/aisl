# Core Evidence Contract Catalog v1

- Core version: `0.44.22`
- Schema: `core_evidence_contract_catalog/v1`
- Execution effect: `none`
- Contracts: `11`

## Boundary

Evidence meaning is selected by `artifact_kind + schema_version`. Task, Suite and Profile identifiers are execution provenance only.

## data-model-candidate-evidence — data-model-candidate-evidence/v1

Lightweight repository-scoped observed evidence used to rank repositories as candidates for deeper data-model analysis.

- Status: `runtime_published`
- Target analyzer: `data-model-candidate-analyzer`
- Consumer knowledge: `data-model-discovery`
- Record limit: `None`

### Payload sections

- `candidate_profile` — identity `repo_id`

### Forbidden semantics

- automatic repository selection
- full data-model construction
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## interaction-boundary-evidence — interaction-boundary-evidence/v1

Deterministic repository-scoped inbound and outbound HTTP boundary observations for cross-repository matching.

- Status: `runtime_published`
- Target analyzer: `interaction-boundary-analyzer`
- Consumer knowledge: `system-interactions`
- Record limit: `None`

### Payload sections

- `repository_identity` — identity `repo_id`
- `boundary_catalog` — identity `artifact_name`

### Forbidden semantics

- cross-repository matching inside Core
- Kafka boundary inference
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## java-persistence-mapping-evidence — java-persistence-mapping-evidence/v1

Explicit Java persistence mapping declarations normalized from observed JPA/Jakarta annotations without matching them to a physical model or inferring default names.

- Status: `runtime_published`
- Target analyzer: `java-persistence-mapping-analyzer`
- Consumer knowledge: `logical-physical-mapping`
- Record limit: `None`

### Payload sections

- `persistence_type_mappings` — identity `persistence_type_mapping_id`
- `persistence_field_mappings` — identity `persistence_field_mapping_id`
- `persistence_key_mappings` — identity `persistence_key_mapping_id`
- `persistence_relationship_mappings` — identity `persistence_relationship_mapping_id`
- `persistence_inheritance_mappings` — identity `persistence_inheritance_mapping_id`
- `mapping_gaps` — identity `mapping_gap_id`

### Forbidden semantics

- matching logical objects to physical tables or columns
- physical-schema substitution
- JPA default table or column naming inference
- naming-similarity matching
- observed SQL or storage usage as mapping proof
- confidence score or probability
- task_id, suite_id or profile_id as semantic selectors

### Current gaps

- Method/property-access annotations are not normalized because java-persistence-mapping-evidence/v1 currently observes type and field declarations only.
- Composite annotations such as JoinColumns, JoinTable and AttributeOverrides are retained as raw source annotations and diagnosed, but not normalized in v1.
- JPA default table and column naming is intentionally not inferred.

### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## java-type-structure-evidence — java-type-structure-evidence/v1

Complete source-observed Java type declarations and their structural members without persistence, physical, usage or effective-model interpretation.

- Status: `runtime_published`
- Target analyzer: `java-type-structure-analyzer`
- Consumer knowledge: `code-declared-data-model`
- Record limit: `None`

### Payload sections

- `source_units` — identity `source_unit_id`
- `type_declarations` — identity `type_id`
- `field_declarations` — identity `field_id`
- `inheritance_declarations` — identity `inheritance_id`
- `annotation_declarations` — identity `annotation_id`
- `type_reference_observations` — identity `type_reference_id`
- `enum_constant_declarations` — identity `enum_constant_id`

### Forbidden semantics

- JPA entity, table, column, key or relationship interpretation
- logical-to-physical mapping
- physical-schema substitution
- SQL or storage usage
- converter or builder attribute mapping
- effective inherited fields
- effective associations
- domain or business-object classification
- confidence score or probability
- task_id, suite_id or profile_id as semantic selectors

### Current gaps

- Java annotation type declarations are diagnosed but not yet materialized as type records.

### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## model-storage-evidence — model-storage-evidence/v1

Observed model-to-storage record identities, reference construction and composed key lineage extracted from framework API bindings without physical-table or business interpretation.

- Status: `runtime_published`
- Target analyzer: `java-model-storage-analyzer`
- Consumer knowledge: `model-storage-semantics, effective-data-model`
- Record limit: `None`

### Payload sections

- `storage_records` — identity `observation_id`
- `storage_references` — identity `observation_id`
- `storage_key_lineage` — identity `observation_id`
- `reference_value_derivations` — identity `observation_id`

### Forbidden semantics

- logical object to SQL or PDM table matching
- logical field to physical column matching
- PK or FK verdicts
- business key classification
- physical-name normalization or separator guessing
- current-version filtering semantics
- confidence scores or candidate ranking
- UCP-specific entity names or source-table hardcodes

### Current gaps

- The first framework interpreter is TSA/change-vector; additional storage encodings require independent interpreters, not hardcoded KLC rules.

### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## persistence-lineage-evidence — persistence-lineage-evidence/v1

Deterministic repository-scoped source-to-storage and storage-to-access persistence lineage evidence with explicit writes, reads, field mappings and gaps.

- Status: `runtime_published`
- Target analyzer: `persistence-lineage-analyzer`
- Consumer knowledge: `persistence-lineage`
- Record limit: `None`

### Payload sections

- `artifacts` — identity `artifact_name`

### Forbidden semantics

- FDP verdict assignment
- business ownership inference
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## reference-data-evidence — reference-data-evidence/v1

Facts-only declared values, literal writes, storage context and unresolved gaps published as typed evidence.

- Status: `runtime_published`
- Target analyzer: `reference-data-analyzer`
- Consumer knowledge: `reference-data`
- Record limit: `None`

### Payload sections

- `sections` — identity `section_plus_relative_path`

### Forbidden semantics

- reference-data or NSI classification
- candidate ownership inference
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## sql-analysis — sql-analysis/v1

Repository SQL analysis evidence

- Status: `runtime_published`
- Target analyzer: `sql-analysis-analyzer`
- Consumer knowledge: `sql-analysis, workspace-sql-catalog`
- Record limit: `None`

### Payload sections

- `canonical_manifest_path` — identity `single_manifest`
- `fact_shards` — identity `fact_type`

### Forbidden semantics

- Task/Suite/Profile semantic routing
- LLM interpretation in canonical evidence
- absolute machine paths

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## storage-usage-evidence — storage-usage-evidence/v1

Observed Java storage usage evidence

- Status: `runtime_published`
- Target analyzer: `java-storage-usage-analyzer`
- Consumer knowledge: `observed-storage-usage`
- Record limit: `None`

### Payload sections

- `storage_accesses` — identity `storage_access_id`
- `storage_reads` — identity `storage_read_id`
- `storage_writes` — identity `storage_write_id`
- `storage_usage_gaps` — identity `storage_usage_gap_id`

### Forbidden semantics

- physical table inference from repository names
- field lineage without explicit selected or bound fields
- business ownership or risk classification

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## system-description-evidence — system-description-evidence/v1

Deterministic interface, scenario, dependency, storage and access-boundary records published as typed evidence.

- Status: `runtime_published`
- Target analyzer: `system-description-analyzer`
- Consumer knowledge: `system-description`
- Record limit: `None`

### Payload sections

- `artifacts` — identity `artifact_name`

### Forbidden semantics

- business capability classification
- system ownership inference
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## value-flow-evidence — value-flow-evidence/v1

Deterministic repository-scoped atomic value occurrences, direct observed value-flow edges and boundary field contracts.

- Status: `runtime_published`
- Target analyzer: `value-flow-analyzer`
- Consumer knowledge: `repository-value-flow`
- Record limit: `None`

### Payload sections

- `artifacts` — identity `artifact_name`

### Forbidden semantics

- transitive path fabrication inside Core
- business lineage interpretation
- task_id, suite_id or profile_id as semantic selectors
- hidden fallback or dual-write to Task/Suite artifacts

### Current gaps


### Current state

- Source observations available: `True`
- Typed runtime artifact published: `True`
- Runtime status: `registered_in_generic_core_evidence_runtime`

## Next step

compile Knowledge Resolution Plan evidence requirements into core_evidence_execution_request/v1
