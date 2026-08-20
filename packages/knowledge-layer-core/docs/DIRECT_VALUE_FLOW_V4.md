# Direct value-flow graph v4

`repository_value_node` and `repository_value_flow_edge` are the canonical direct value-flow model across selected repositories.

Repository-local nodes and edges are materialized directly from observed `catalog/field_occurrences.json` and `catalog/field_flow_edges.json`. HTTP wire nodes come from compact interface contracts. Cross-repository transport edges are added only for confirmed `system_boundary_interaction` rows and exact unique normalized wire paths. No edge depends on an ingress execution path or precomputed transitive lineage path.

## Value nodes

Nodes have a stable `value_node_id`, repository identity, typed `node_kind`, operation,
display reference, optional type and wire path, and exact provenance back to the source
field-occurrence record.

Node kinds are:

- `field`
- `parameter`
- `return_value`
- `local_value`
- `wire_field`
- `database_column`
- `constant`
- `configuration`
- `generated_value`
- `derivation`

Static constant accesses such as `Boolean.TRUE` and upper-case Java constants are typed as
`constant`; they are not treated as source attributes and cannot create a false rename.

## Direct edges

Every row represents one observed transition only. The materializer never creates a
shortcut edge for a longer path.

Each edge has explicit `source_repo_id` and `target_repo_id`. They are equal for repository-local facts and differ for cross-repository transport.

Each edge records:

- `flow_kind`
- original `source_edge_kind`
- `transformation_kind`
- `naming_relation`
- `value_preservation`
- `confidence`
- optional `derivation_id`
- optional `derivation_kind`
- `derivation_source_count`
- guards and provenance

## Naming semantics

A rename is published only when both direct edge endpoints are observed field nodes and
their terminal property names differ.

Example:

```text
source.surname -> target.familyName
transformation_kind = identity
naming_relation = renamed
value_preservation = preserved
```

This is a local evidence statement. It does not create a global semantic identity between
`surname` and `familyName`.

## Transformation semantics

Transformation classification uses only explicit edge metadata or observed AST expression
text already published by core.

Supported values:

- `identity` — direct mechanical transfer
- `extracted` — field projection
- `normalized` — observed trim/case/canonicalization operation
- `formatted` — observed formatter operation
- `hashed` — observed hash/digest operation
- `combined` — observed string/collection combination
- `derived` — conditional, arithmetic or known conversion/helper derivation
- `unknown` — an observed invocation is involved but the transformation cannot be classified safely

Value preservation:

- `identity`, `extracted` -> `preserved`
- `normalized`, `formatted`, `combined` -> `partially_preserved`
- `hashed`, `derived` -> `transformed`
- `unknown` -> `unknown`

The payload records `transformation_basis` so consumers can distinguish explicit metadata
from expression-based classification.

## Derivation grouping

All direct contributors to the same observed expression or conditional result share a
stable `derivation_id`. The edge also exposes `derivation_kind` and
`derivation_source_count`.

For:

```text
firstName + " " + lastName -> fullName
```

three direct edges remain:

```text
firstName -> expression
lastName -> expression
expression -> fullName
```

All three carry the same derivation identifier and source count `2`. No synthetic
`firstName -> fullName` or `lastName -> fullName` shortcut is created.

Constants and generated values remain typed source nodes. Whole-object participation
remains a direct edge fact; it is not eagerly expanded into synthetic field paths or a
separate object-lineage table.

## Removed eager models

The following eager derived stores remain intentionally absent:

- `system_interaction_attribute_lineage`
- `system_interaction_object_lineage`
- `system_interaction_value_origin`

Full and partial attribute paths will be resolved from direct nodes and edges by a bounded
resolver in a later iteration.

## HTTP transport edges

Confirmed HTTP boundaries add direct wire-to-wire edges for exact unique normalized paths:

```text
outbound request wire in source -> inbound request wire in target
inbound response wire in target -> outbound response wire in source
```

Request and response directions follow message flow. Transport is not emitted for probable, ambiguous or unresolved boundaries. The edge preserves `boundary_interaction_id`, both interface IDs, contract evidence and exact match basis. Execution context is optional and is not consulted.
