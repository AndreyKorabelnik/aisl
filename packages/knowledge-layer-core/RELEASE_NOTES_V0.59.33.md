# knowledge-layer-core 0.59.33

Add an agent-ready data-model attribute-extension context as a separate KLC materialization above existing evidence/knowledge layers.

## Purpose

Provide another agent with actionable, evidence-grounded JOIN semantics for extending an existing datamart without moving SQL-generation logic into KLC and without requiring the consumer to manually reconcile several lower-level knowledge artifacts.

## Architecture

New materialization: `data-model-attribute-extension-context`.
Produced schema: `data-model-attribute-extension-context/v1`.

Inputs are existing knowledge only:
- code-declared data model;
- model storage semantics;
- logical/storage mapping;
- cross-artifact data-model mapping;
- SQL analysis.

No new Core analyzer is introduced. `cross-artifact-data-model-mapping/v6` is unchanged so its existing consumers remain on the generic correspondence/lineage layer.

## Join semantics

The materialization distinguishes:
- `equals`;
- `derive_source_identity_from_target_key`;
- `resolve_reference_value_to_target_key`;
- `resolve_reference_collection`;
- `not_established`.

It preserves cardinality, polymorphism, key/reference expressions, exact structural correspondences, observed SQL anchors and joins, physical candidates when actually observed, provenance, confidence and diagnostics.

It does **not** emit SQL and does not infer business meaning. Missing physical representation remains visible as a gap/diagnostic.

## Reuse

The existing exact structural reference-value/key correspondence logic was extracted into a shared canonicalizer and reused by both the legacy workspace data-model path and the new typed materialization. No second expression-matching algorithm was added.
