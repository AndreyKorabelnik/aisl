# knowledge-layer-core 0.52.4

Iteration 88: exact model-field storage observations.

## Changes

- Enriched the existing `model_object_fields` query with exact converter storage observations.
- Correlation requires both:
  - an exact literal `alias("<model FQCN>")` in the converter method;
  - an exact literal `primitiveField("<model field name>", <expression>)` in the same converter method.
- Preserved the value expression without interpreting business identity or runtime semantics.
- Added portable evidence references with converter repository, source path, line range, extractor and role.
- No new materialized tables, no schema migration and no change to code-analyzer-core.
- Existing Knowledge Layers can be queried without rematerialization.

## Validation

- compileall: passed
- focused KLC tests: 10 passed
- real UCP query smoke: passed
- full test suite: not run; materialization and core extraction were unchanged
