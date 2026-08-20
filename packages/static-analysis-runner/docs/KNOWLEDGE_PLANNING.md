# Knowledge planning v2

The user selects knowledge and scope. The user does not define Core stages, analyzers, Tasks, Suites or KLC materializations.

```text
knowledge_profile/v2
  -> knowledge_catalog/v2
  -> knowledge_resolution_plan/v2
```

## Data-model knowledge

Different sources produce different knowledge:

- `code-declared-data-model` — types, fields, declared relations and inheritance from source code;
- `physical-data-model` — tables, columns, keys, constraints and physical relationships;
- `logical-physical-mapping` — persistence mappings between the two independent models;
- `sql-source-inventory` — observed SQL usage;
- `observed-storage-usage` — observed code-level reads and writes;
- `effective-data-model` — explicit KLC composition over the independent knowledge models.

The resolver never treats source-code structure and physical schema as interchangeable inputs.

## `knowledge_catalog/v2`

The catalog is compiled from official KLC, Core, Runner execution-result and responsibility-map contracts. It shows:

- business contents of every knowledge type;
- required and optional evidence sources;
- required and optional KLC knowledge-model dependencies;
- current runtime availability and typed-contract readiness;
- technical Core stage and Foundation lineage only for advanced diagnostics;

## `knowledge_profile/v2`

The profile contains repository/workspace scope, selected knowledge and business-level presentation/coverage options. Technical identifiers remain forbidden.

When a composite knowledge type is selected, required knowledge dependencies are added automatically. Recommended dependencies remain optional and are reported as diagnostics.

## `knowledge_resolution_plan/v2`

The read-only plan distinguishes:

- user-requested knowledge;
- implicitly added required knowledge;
- typed evidence requirements;
- KLC model dependencies;
- current Core stage sources;
- Foundation requirements;
- current-vs-target readiness.

The plan does not inspect repository contents and does not execute analysis.

## Declarative `knowledge_product_catalog/v1`

User-facing knowledge product definitions are not embedded in Runner Python code.
Runner loads the versioned declarative catalog from the packaged resource
`static_analysis_runner/resources/knowledge-product-catalog.v1.json` by default.
The `knowledge-catalog` command may use another validated catalog with
`--knowledge-product-catalog`.

The product catalog owns business-facing metadata and selection policy:

- `knowledge_id` and the referenced technical `materialization_id`;
- title, summary, category and contents;
- repository/workspace scopes;
- required and recommended knowledge dependencies;
- selection/input-mode notes;
- explicit internal materializations that are not user-selectable.

`knowledge_id` and `materialization_id` are deliberately different identities.
Multiple user-facing knowledge products may reference one technical materialization.
Adding such a product does not require a Runner Python-code change.

The loader validates the catalog fingerprint, unique product identities, supported
scopes, dependency references and dependency cycles. There is no fallback to a
Python policy dictionary when the catalog is missing or invalid.

The compiled `knowledge_catalog/v2` records the source product catalog schema,
fingerprint, catalog ID and source kind together with the existing KLC/Core/Runner
contract fingerprints.


### Internal materializations required by a public Knowledge Product

A public catalog entry may declare `required_internal_materializations`. These are Runner-owned planning dependencies: they are automatically added to the technical DAG, remain non-selectable to the user, and must resolve to entries in the catalog `internal_materializations` list. This does not create a second public Knowledge Product.
