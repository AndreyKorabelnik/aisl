# code-analyzer-core 0.39.0

Iteration 20 introduces generic storage-record and storage-reference evidence.

## Changes

- Java calls, assignments and returns now retain byte positions and lexical-scope boundaries.
- Local-variable resolution selects the nearest visible dominating assignment and fails closed on genuine ambiguity.
- Interprocedural evidence links call results to callee return expressions.
- Builder key and alias assignments on the same receiver are materialized as `storage_record_observation`.
- Reference assignments whose value originates from a returned storage key are materialized as `storage_reference_observation`.
- Builder API roles are supplied by analysis-profile configuration; analyzer logic does not depend on UCP classes, packages, field names or fixed method names.
- Physical encoding remains `downstream_interpretation_required`; core adds no separator, alias normalization, SQL or join verdict.

## Compatibility

The new fact types are additive repository evidence. Public data-model JSON is not changed in this release.
