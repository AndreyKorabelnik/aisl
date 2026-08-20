# knowledge-layer-core 0.59.19

## Reusable observed-producer SQL column traversal

The recursive physical-relation producer traversal previously embedded inside
`cross_artifact_data_model_builder` is now a reusable KLC component:

- `ObservedMaterializationIndex` resolves same-workflow or nearest observed upstream producers only;
- `SqlProducerColumnTraversal` composes physical relation columns through observed producer queries and projections;
- physical relations with no observed producer remain terminal origins;
- no `stg_*`, semantic-role, Gold-data, or schema-name heuristics are introduced;
- existing cross-artifact value-origin behavior continues to use the same rules through the shared component.

This is the first implementation step toward product S2T ultimate-source lineage. It does not yet change the SQL target-column API surface.
