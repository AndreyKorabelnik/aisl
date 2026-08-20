# knowledge-layer-core 0.40.0

## Repository identity metadata for topology boundaries

- Replaced the implicit repository-alias map with a canonical repository identity model.
- Repository HTTP boundaries now publish `system_id`, `project_id` and configured service aliases.
- Configured repository aliases participate in inbound service identity matching.
- Administrative `project_id` remains metadata only and never creates an interaction edge.
- Boundary query and evidence interfaces support `system_id` and `project_id` filters.
- The suite schema is now `knowledge_layer_suite_scope/v9`.
- No legacy boundary schema, compatibility view or dual-write path is retained.

## Validation

A four-repository fixture places two independent service pairs in the same project and gives both pairs the same HTTP method/path. Configured service aliases disambiguate the targets, while weak connected components remain two separate strict islands.
