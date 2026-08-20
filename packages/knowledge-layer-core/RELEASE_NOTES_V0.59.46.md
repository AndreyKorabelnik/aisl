# knowledge-layer-core 0.59.46

## Change

- `cross-artifact-data-model-mapping` now materializes its insert-heavy build inside one explicit DuckDB transaction.
- No schema, contract, mapping rule, confidence rule, capability, compatibility path, or fallback changed.
- The change removes per-row autocommit overhead exposed by the real UCPDataModel + UCPucp-tsa-v4 + datamart_profile_fl + PDM workflow.

## Scope

Generic KLC runtime performance fix only. It follows the same transaction discipline introduced for `logical-storage-mapping` in 0.59.45.
