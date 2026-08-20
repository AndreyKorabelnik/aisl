# Release notes — code-analyzer-core 0.41.8

Iteration 55 adds a new scoped direct column-lineage contract built only from validated write-target, projection, column-usage, and relation facts.

## Changes

- Added canonical `sql_direct_column_lineage` facts.
- Added canonical `sql_scoped_lineage_gap` diagnostics.
- Direct lineage is built through the validated chain:
  `write target -> target/projection binding -> scoped projection -> scoped column usage -> scoped relation`.
- Nested CTE projections can no longer be attached directly to the final target.
- Direct edges distinguish confirmed target mappings, inferred target names, and partial mappings.
- Multi-input expressions emit one direct edge per source-column occurrence while retaining the shared transformation expression.
- Physical origin status distinguishes physical, logical physical-template, intermediate CTE/derived, not-applicable expression, and unresolved source.
- Expressions without source columns, including constants and runtime functions, are preserved as explicit lineage inputs.
- Bare semantic parameters such as `$app.ctl.loading` are modeled as `semantic_parameter`, never as columns of the only relation in scope.
- Ambiguous/unresolved source relations, partial target mappings, missing projections, and wildcard targets create localized scoped lineage gaps instead of false edges.
- Explicit target columns backed by an unexpanded wildcard receive the dedicated `wildcard_projection_unexpanded` diagnostic.
- Package and runtime version metadata are synchronized at `0.41.8`.
- Existing legacy `mart_column_lineage` remains temporarily available only for comparison; it is not merged into the new contract.

## Compatibility

No compatibility adapter is provided. `sql_direct_column_lineage` is the canonical direct lineage model for subsequent recursive CTE/derived traversal.
