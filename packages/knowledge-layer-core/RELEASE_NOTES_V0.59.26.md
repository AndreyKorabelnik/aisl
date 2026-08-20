# knowledge-layer-core 0.59.26

## Change

Completes product S2T producer traversal for materialized SQL queries with compatible top-level set branches (`UNION`/set-operation roots).

`ObservedMaterializationIndex` now accepts multiple top-level producer scopes only when every branch has a complete and compatible output contract. `SqlProducerColumnTraversal` then follows the requested column through every compatible branch. Conflicting branch contracts remain unresolved and are never guessed.

The cross-artifact builder now delegates producer output-contract resolution to the same reusable component instead of retaining a shadow copy of older logic.

## Real epk_client result

- `client_centaur_flag` now traverses the observed `stg_epk_client_centaur_flag.sql` UNION producer and reaches both proven terminal sources (`Equivalent.key` and `MergeClientInfo.key`).
- All 86 Gold target fields now have product value mappings.
- `epk_id` remains exactly current/history `Individual.id`.
- Full evidence-backed comparison reaches 112/132 supplied Gold mappings after evaluation-only schema-placeholder normalization; runtime placeholders remain unresolved unless observed bindings exist.
