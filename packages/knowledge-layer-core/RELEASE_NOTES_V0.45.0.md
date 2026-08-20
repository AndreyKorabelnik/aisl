# knowledge-layer-core 0.45.0

## HTTP wire representation in the direct value-flow graph

- Added typed `wire_field` value nodes from HTTP request and response contract signatures in `system_interface_catalog.json`.
- Added repository-local serialization and deserialization edges for all four HTTP message directions:
  - outbound request: local field -> wire field;
  - inbound request: wire field -> local field;
  - inbound response: local field -> wire field;
  - outbound response: wire field -> local field.
- Kept wire materialization independent from cross-repository boundary matching: unmatched interfaces still publish their local wire nodes.
- A local wire binding is emitted only when one unique boundary occurrence matches the exact operation, payload role and normalized wire path.
- Ambiguous local candidates leave the wire node visible without inventing an edge.
- Reused the canonical `repository_value_node` and `repository_value_flow_edge` tables; no parallel serialization model was introduced.
- Kept all logic protocol-, repository-, class-, method- and field-neutral.

## Schema

- package: `knowledge-layer-core 0.45.0`
- suite schema: `knowledge_layer_suite_scope/v13`
- direct graph schema: `repository_value_flow/v3`

## Scope intentionally deferred

- Cross-repository HTTP transport edges are not part of this release.
- Attribute-path traversal is not part of this release.
- Custom serializers, XML, protobuf and Kafka wire formats are not inferred.
