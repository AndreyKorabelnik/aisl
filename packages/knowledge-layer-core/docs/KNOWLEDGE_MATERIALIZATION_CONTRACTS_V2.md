# Knowledge Materialization Contracts v2

`knowledge_materialization_catalog/v2` is a read-only KLC-owned catalog.

## Core rule

Different evidence source families produce different knowledge. KLC does not use Java structure, physical schema, persistence mapping or observed usage as alternative ways to create one undifferentiated model.

## Data-model decomposition

- `code-declared-data-model` — types, fields, declared relations and inheritance observed in source code.
- `physical-model` — tables, columns, keys, constraints and physical relationships.
- `logical-physical-mapping` — explicit persistence mappings between the code-declared and physical models.
- `observed-storage-usage` — observed reads, writes and storage access from code.
- `sql-analysis` — observed SQL statements, roles, joins and source-to-target lineage.
- `effective-data-model` — KLC composition over independent models; it preserves the origin of every layer.

`effective-data-model` requires the code-declared model, physical model and logical-physical mapping. SQL and storage usage are optional model inputs that enrich the view without changing declared semantics.

## Legacy umbrella

`code_conceptual_model/v2` mixes multiple knowledge families. The catalog routes 27 legacy sections to their target owners. Mixed sections such as `entities` and `associations` are split by evidence semantics instead of copied as a whole.

## Runtime

The current KLC-owned runtime handlers are `code-declared-data-model`, `physical-model`, `logical-physical-mapping` and `effective-data-model`. Runtime dispatch is `materialization_id → KLC-owned handler`; Task, Suite and Core Profile semantics are not used.

## Effective model composition

`effective-data-model` is a logical-first composition. Every code-declared type and effective field remains a logical object. Physical tables, columns, keys and relationships are attached only through `logical-physical-model-mapping/v1` records whose status is `matched`. Physical objects that are not mapped remain in a separate unmapped-object inventory and are never promoted to logical entities.

Inherited fields are not assigned a physical column owned by a different logical type unless explicit persistence-inheritance evidence exists. SQL and observed-storage-usage inputs are optional enrichments; when present they are recorded as source layers and cannot override declared or physical semantics.

`model-domain-cluster-view/v1` contains deterministic technical groupings: package-derived domains and weakly connected components of declared relationships. It does not claim business-domain meaning.
