# knowledge-layer-core 0.47.0

## Canonical bounded attribute-path resolver

- Adds `repository_attribute_path/v1`.
- Resolves complete and partial paths over the direct value-flow graph only.
- Requires an explicit repository selection.
- Supports exact source/target reference resolution, confidence and edge-kind filters,
  cycle prevention, branching bounds, hop bounds and path-count bounds.
- Preserves every direct edge's transformation, rename, value-preservation, confidence
  and provenance.
- Returns explicit gaps rather than dropping partial paths.
- Validates a complete HTTP cross-repository path independent of execution context.

## Legacy removal

- Removes `knowledge_layer_core/path_queries.py`.
- Removes `knowledge_layer_core/field_flow.py`.
- Removes `common.path-queries` and `common.field-flow-queries` capabilities.
- Removes the six old neighborhood/reachability/path/field-flow evidence commands.
- Removes their tests and obsolete bounded-path document.
- Adds no compatibility aliases or dual execution.

## Contracts

- package: `0.47.0`;
- suite schema: `knowledge_layer_suite_scope/v15`;
- direct graph schema remains `repository_value_flow/v4`;
- resolver schema: `repository_attribute_path/v1`.
