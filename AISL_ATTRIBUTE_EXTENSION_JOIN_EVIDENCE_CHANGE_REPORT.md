# AISL attribute-extension JOIN evidence — change report

Date: 2026-08-15  
Status: **ATTRIBUTE_EXTENSION_JOIN_EVIDENCE_BLOCK_COMPLETE**

## Why this block changed code

A real attribute-extension acceptance for **«название региона рождения клиента»** proved two narrow read-surface gaps in the existing typed `data-model-attribute-extension-context/v1` owner:

1. Core/model-storage evidence already observed the relationship storage reference field and its derivation, but the attribute-extension context did not expose that storage-field observation/provenance explicitly enough for a consumer to distinguish it from an assumed existing SQL column.
2. SQL JOIN examples were returned from source/target object anchors without an explicit exact-vs-related relevance label. Real analog JOINs were useful evidence but could be overclaimed as an already-existing exact JOIN.

No new analyzer, materializer, Knowledge API path, graph model or compatibility layer was introduced.

## KLC 0.61.0a31

`data-model-attribute-extension-context/v1` now preserves existing model-storage evidence in `basis.source_storage_field_observations` including:

- storage-reference field name;
- observed reference operation;
- reference value expression;
- source owner/operation;
- repository/source refs and provenance.

It also publishes:

- `source_storage_field_observation_count`;
- `source_relationship_field_observed_in_sql`;
- `exact_relationship_sql_join_observed`;
- `sql_join_example_relevance_counts`.

Each returned observed SQL JOIN example is classified with `relationship_relevance`, including exact source-field→target-key matches and explicitly labeled related/analog evidence. Analogs remain available because they are useful knowledge; they are not silently discarded.

New diagnostics make uncertainty actionable instead of collapsing it to unresolved:

- `storage_reference_field_not_observed_in_current_sql`;
- `observed_sql_join_examples_are_related_analogs`.

Confirmed structural/storage encoding remains confirmed when its own evidence supports it; only the SQL proposal confidence is bounded by the missing exact SQL observation.

## Knowledge Integration 0.1.9

Attribute-addition profile v11 and tool catalog v3 now instruct consumers to:

- treat storage-reference observations as observed storage evidence, not automatically as observed SQL columns;
- prioritize exact JOIN examples;
- use labeled analog examples as supporting evidence for a `strongly_supported` proposal;
- keep the missing-current-SQL diagnostic visible rather than returning an unhelpful blanket `unresolved`.

## Unchanged owners

No implementation change in:

- code-analyzer-core;
- static-analysis-runner;
- prepared-knowledge-runtime;
- knowledge-api;
- knowledge-control-plane;
- AISL contract.

Core already owned the necessary observed facts; the generic fix belongs to KLC composition/consumer guidance.
