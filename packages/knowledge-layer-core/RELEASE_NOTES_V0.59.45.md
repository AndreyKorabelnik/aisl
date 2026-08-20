# knowledge-layer-core 0.59.45

## Change

- `logical-storage-mapping` now executes its row materialization inside one explicit DuckDB transaction.
- No schema, contract, mapping rule, confidence rule, or capability changed.
- The change removes per-row autocommit overhead observed on the real UCP TSA storage evidence.

## Scope

Generic KLC runtime performance fix only. No compatibility path, fallback, or application-specific rule was added.
