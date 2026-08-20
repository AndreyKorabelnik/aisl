# knowledge-layer-core 0.43.0

## Canonical repository direct value-flow graph

This release replaces eager cross-system request/response attribute paths, whole-object paths and request value-origin paths with one repository-local graph of typed value nodes and direct observed edges.

The graph is materialized from existing `catalog/field_occurrences.json` and `catalog/field_flow_edges.json` evidence. It is independent from cross-repository boundary matching and from optional ingress-to-outbound execution contexts.

## Removed models

The following tables, materializers, queries, evidence tools and capabilities are removed without compatibility aliases:

- `system_interaction_attribute_lineage`
- `system_interaction_object_lineage`
- `system_interaction_value_origin`

## New models

- `repository_value_node`
- `repository_value_flow_edge`

Every edge represents one observed transition only. No transitive shortcut is materialized.
Constants and generated-time expressions are typed source nodes in the same graph.

## Complexity reduction

Four eager materializer modules totaling 3,263 lines were removed. The new canonical direct graph materializer is 369 lines, a net reduction of 2,894 lines in the replaced materialization core.

## Known limitation

A bounded attribute-path resolver is not part of this release. Consumers can inspect direct nodes and edges, but full and partial transitive paths will be restored through the new resolver rather than through legacy eager tables.
