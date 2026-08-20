# knowledge-layer-core 0.20.0

## Purpose

Adds the first public, typed data-model query surface shared by report builders and grounded assistants. Consumers no longer need direct SQL against the Knowledge Layer.

## Added

- `DataModelQueryService` with deterministic operations for object search, object detail, fields, keys, relationships, join guidance, and cross-repository correspondences.
- Batch source-observation evidence resolution to avoid N+1 evidence lookups.
- Stable query result envelopes with scope, items, summary, evidence, gaps, and deterministic ordering.
- Real UCP workspace contract tests.

## Important semantics

- Model object classification is generic and based on observed annotation-name patterns; the core does not hard-code UCP annotation names or repository paths.
- Original annotation facts and the classification basis are retained.
- Join guidance describes observed logical encoding. It never upgrades that evidence to a confirmed physical SQL join or foreign key.

## Validation

- 135 passed, 6 skipped, 0 failed.
- The two historically long combined-process files were also run test-by-test; all 38 individual tests passed.
- Real UCP workspace: 1,326 types, 504 model relationships, 862 cross-repository type resolutions.
