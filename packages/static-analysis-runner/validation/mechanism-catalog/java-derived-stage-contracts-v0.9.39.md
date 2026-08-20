# Java derived-evidence stage contracts

This is a read-only description of the current Core implementation. It is not a runtime registry.

## Summary

- contracts: 9
- ready for Suite reuse: 4
- conditional: 4
- blocked: 1

| Stage | Reads AnalysisResult | Upstream dependencies | Current serialization | Suite reuse |
|---|---|---|---|---|
| `declared_value_summary_scan` | none | declared_value_scan_optional | facts are persisted by later packaging; status has dedicated JSON | **conditional** |
| `java_data_flow_build` | none | — | facts are only persisted by later normalized/compact packaging; status has dedicated JSON | **ready** |
| `java_data_model_candidate_scan` | none | — | dedicated candidate-profile JSON plus facts later serialized by normal packaging | **ready** |
| `java_data_model_lineage_build` | none | java_persistence_lineage_build_optional | facts are only persisted by later normalized/compact packaging; progress/status have dedicated JSON | **blocked** |
| `java_field_flow_build` | selected_sections | java_structural_scan | facts are only persisted by later normalized/compact packaging; status has dedicated JSON | **conditional** |
| `java_persistence_lineage_build` | none | — | facts are only persisted by later normalized/compact packaging; progress/status have dedicated JSON | **ready** |
| `java_system_interaction_enrichment` | selected_sections | config_scan, java_structural_scan | facts/interfaces are persisted through Foundation or normal package; status has dedicated JSON | **ready** |
| `java_table_observation_build` | complete_fact_list_parameter_but_narrow_actual_filter | java_structural_scan, db_schema_scan | dedicated data-model observation artifact plus facts in normal package | **conditional** |
| `java_traceability_build` | none | java_data_flow_build | facts are only persisted by later normalized/compact packaging; status has dedicated JSON | **conditional** |

## `declared_value_summary_scan`

Build bounded summaries from raw declared-value facts.

**Requires**

- `declared_value_facts_or_repository_file_inventory`
- `declared_value_status_optional`

**Provides**

- `declared_value_set_summary`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(declared_value_summary_facts)`
- mutates: `coverage[declared_value_set_summary]`

**Suite reuse**

- status: **conditional**
- key: `declared_value_fact_bundle_fingerprint`
- key: `summary_policy_version`
- blocker: three fallback input paths are selected from pipeline history rather than one required input contract
- action: Keep in Core; require a typed declared-value fact bundle and remove repository-rescan fallback from the summary producer.

**Fallback:** Uses current-stage raw facts, Foundation optional facts, or rescans repository files when neither is available.

## `java_data_flow_build`

Build lightweight method-parameter and field-to-outbound-sink flow evidence.

**Requires**

- `repository_file_inventory`

**Provides**

- `source_to_sink_flow`
- `field_identifier_flow`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(flow_facts)`
- mutates: `coverage[java_data_flow]`

**Suite reuse**

- status: **ready**
- key: `repository_snapshot`
- key: `java_parser_version`
- key: `data_flow_builder_version`
- action: Keep in Core and make its fact bundle a reusable typed artifact.

## `java_data_model_candidate_scan`

Detect repository-level evidence that the repository contains a data model worth deeper analysis.

**Requires**

- `repository_root`
- `repository_file_inventory`
- `repo_id`
- `project_code`
- `system_name`
- `core_version`

**Provides**

- `data_model_candidate`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(candidate_facts)`
- mutates: `coverage[data_model_candidate_scan]`

**Suite reuse**

- status: **ready**
- key: `repository_snapshot`
- key: `core_version`
- key: `candidate_policy_implementation`
- action: Keep in Core as evidence and allow one execution per repository snapshot.

## `java_data_model_lineage_build`

Build attribute occurrence, mapping, derivation, structure and lineage-gap evidence.

**Requires**

- `repository_file_inventory`
- `repository_metadata`
- `model_annotation_contracts`
- `persistence_facts_optional`
- `persistence_status_optional`

**Provides**

- `attribute_occurrence`
- `persistent_structure`
- `attribute_mapping`
- `attribute_derivation`
- `lineage_gap`
- `type_inheritance`
- `effective_entity_field`
- `effective_entity_association`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(data_model_facts)`
- mutates: `coverage[java_data_model_lineage]`

**Suite reuse**

- status: **blocked**
- key: `repository_snapshot`
- key: `repository_metadata`
- key: `max_depth`
- key: `model_annotation_contracts`
- key: `persistence_fact_bundle_fingerprint`
- key: `include_persistence_facts`
- blocker: output composition changes depending on whether persistence was requested as a separate stage
- blocker: the builder can execute persistence internally
- blocker: include_persistence_facts is controlled by pipeline history rather than profile contract
- action: Split internal persistence fallback from data-model lineage and make persistence a required typed input; package persistence facts independently.

**Fallback:** If persistence facts are absent, the builder runs persistence lineage internally. It may also copy persistence facts into its own output when include_persistence_facts=true.

## `java_field_flow_build`

Build local and bounded interprocedural field-flow evidence.

**Requires**

- `repository_file_inventory`
- `interfaces`
- `schemas`
- `repository_id`
- `repository_root`

**Provides**

- `field_flow_facts`

**AnalysisResult interaction**

- read mode: `selected_sections`
- reads: `interfaces`
- reads: `schemas`
- mutates: `facts.extend(field_flow_facts)`
- mutates: `coverage[java_field_flow]`

**Suite reuse**

- status: **conditional**
- key: `repository_snapshot`
- key: `interfaces_fingerprint`
- key: `schemas_fingerprint`
- key: `field_flow_builder_version`
- blocker: interfaces and schemas are passed as mutable result sections without independent artifact fingerprints
- action: Keep in Core; persist and fingerprint the required interface/schema inputs before suite reuse.

## `java_persistence_lineage_build`

Build neutral source-to-storage and storage-access lineage evidence.

**Requires**

- `repository_file_inventory`

**Provides**

- `data_source`
- `persistent_write`
- `stored_data_access`
- `persistence_mapping_hint`
- `source_inspection_request`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(persistence_facts)`
- mutates: `coverage[java_persistence_lineage]`
- mutates: `coverage[java_persistence_runtime_guard]`

**Suite reuse**

- status: **ready**
- key: `repository_snapshot`
- key: `max_depth`
- key: `deep`
- key: `persistence_builder_version`
- action: Keep in Core and make the fact/status bundle a first reusable suite-local derived-evidence artifact.

## `java_system_interaction_enrichment`

Compose local HTTP/configuration boundary evidence without cross-repository matching.

**Requires**

- `repository_file_inventory`
- `config_facts`
- `schemas`
- `interfaces`

**Provides**

- `configuration_value_binding`
- `interaction_boundary_facts`
- `enriched_interface_observations`

**AnalysisResult interaction**

- read mode: `selected_sections`
- reads: `config_facts`
- reads: `schemas`
- reads: `interfaces`
- mutates: `facts.extend(interaction_facts)`
- mutates: `interfaces mutated by scanner`
- mutates: `warnings.extend(interaction_warnings)`
- mutates: `coverage[java_system_interaction_enrichment]`

**Suite reuse**

- status: **ready**
- key: `repository_snapshot`
- key: `config_facts_fingerprint`
- key: `schemas_fingerprint`
- key: `interfaces_fingerprint`
- key: `scanner_version`
- action: Keep in Core and continue sharing through Foundation; make interface mutation explicit in the contract.

## `java_table_observation_build`

Build observed JPA/jOOQ relationship and key-usage evidence.

**Requires**

- `repository_root`
- `repository_file_inventory`
- `repo_id`
- `facts`
- `db_schema`

**Provides**

- `table_relationship_observation`
- `table_key_observation`

**AnalysisResult interaction**

- read mode: `complete_fact_list_parameter_but_narrow_actual_filter`
- reads: `facts filtered to jpa_entity and jpa_relationship`
- reads: `db_schema`
- mutates: `facts.extend(table_observation_facts)`
- mutates: `coverage[java_table_observations]`
- mutates: `coverage[data_model_table_observations]`
- mutates: `table_observations aggregate`

**Suite reuse**

- status: **conditional**
- key: `repository_snapshot`
- key: `jpa_entity_fact_fingerprint`
- key: `jpa_relationship_fact_fingerprint`
- key: `db_schema_fingerprint`
- key: `table_observation_scanner_version`
- blocker: function accepts the complete mutable fact list although it currently reads only two fact types
- blocker: input fact types have no independent persisted fingerprint
- action: Keep in Core; narrow the function signature to typed JPA facts and DB schema, then execute once per Suite.

## `java_traceability_build`

Build bounded ingress/call/storage traces and field-level provenance from Java source evidence.

**Requires**

- `repository_file_inventory`
- `java_data_flow_facts`

**Provides**

- `origin_facts`
- `method_call_facts`
- `storage_access_facts`
- `trace_facts`
- `field_lineage_facts`
- `output_provenance_facts`
- `call_chain_diagnostics`
- `jooq_batch_bind_mappings`

**AnalysisResult interaction**

- read mode: `none`
- mutates: `facts.extend(trace_facts)`
- mutates: `coverage[java_traceability]`

**Suite reuse**

- status: **conditional**
- key: `repository_snapshot`
- key: `java_data_flow_fact_bundle_fingerprint`
- key: `traceability_builder_version`
- blocker: the upstream data-flow bundle has no independent persisted contract/fingerprint
- action: Keep in Core; publish data-flow and traceability as separate typed evidence bundles with explicit dependency.

**Fallback:** If java_data_flow_build is absent, the pipeline supplies an empty fact list and traceability still builds source/call/storage evidence.
