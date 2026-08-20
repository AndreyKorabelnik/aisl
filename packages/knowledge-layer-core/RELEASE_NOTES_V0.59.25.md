# knowledge-layer-core 0.59.25

## Change

Hardens the product S2T value-origin boundary.

A terminal SQL path is promoted to `sql_target_value_source_mapping` only when both source relation identity and source column identity are observed. Paths such as `${hash_val_expr}` / `${row_hash_expr}` that have no terminal relation are preserved in the raw S2T/explain layer, marked unresolved, and published as `ultimate_source_identity_unresolved` gaps.

This prevents null `relation.column` pairs from being represented as resolved value sources and keeps the compact Knowledge API surface evidence-backed.
