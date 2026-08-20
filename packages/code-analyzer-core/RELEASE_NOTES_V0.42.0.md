# Release notes — code-analyzer-core 0.42.0

Iteration 57 adds branch-preserving recursive SQL column lineage through CTE and derived relations.

## Changes

- Added canonical `sql_recursive_column_lineage` facts.
- Traversal starts from validated `sql_direct_column_lineage` edges and follows intermediate relation definitions through `source_scope_ids`.
- Multi-level CTE and derived chains are resolved to terminal physical/template columns, semantic parameters, expressions without source columns, or explicit unresolved boundaries.
- Every `UNION`, `INTERSECT`, and `EXCEPT` output branch is retained.
- Set-operation fields use output ordinal correspondence; branch-local output aliases may differ without losing the branch.
- Added safe on-demand wildcard passthrough:
  - unqualified `*` is traced only when the defining scope has exactly one source relation;
  - qualified `alias.*` is traced only when the alias resolves uniquely;
  - ambiguous multi-source wildcards remain partial.
- Added cycle detection and a configurable maximum traversal depth (default 32).
- Added localized recursive gap kinds for missing projections, ambiguous/unresolved sources, unsupported wildcard traversal, cycles, and depth exhaustion.
- Added deterministic de-duplication of semantically identical terminal paths and recursive gaps.
- Each path contains branch steps, transformation steps, terminal source identity, recursion depth, source resolution status, target mapping status, and repository-relative evidence.
- Added recursive lineage artifacts to full, compact, fact-type, navigation, and package-manifest outputs.
- SQL profile schema version advanced from `1.0` to `1.1`.
- Package and runtime versions are synchronized at `0.42.0`.

## Compatibility

No compatibility adapter is provided. `sql_recursive_column_lineage` is the canonical end-to-end scoped SQL field path. `sql_direct_column_lineage` remains the canonical first-hop fact and is retained as its input, not as a competing recursive model.
