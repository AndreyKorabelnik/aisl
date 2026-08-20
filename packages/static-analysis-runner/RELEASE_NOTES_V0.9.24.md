# static-analysis-runner 0.9.24

- Adds the `interaction-lineage` task and `system-interaction-lineage` suite.
- Supports `knowledge-layer-core>=0.49.1,<1.0.0`.
- Replaces exact Knowledge Layer version equality with a minimum-version and required-public-API compatibility check.
- Replaces `selected_repository_sources/v1` with v2 and propagates per-repository system/project/service aliases into suite materialization.
