# Iteration 28.2E validation — code-analyzer-core 0.40.6

## Result

The second constructor data-flow patch was validated on the real AT900 repository.

- focused constructor tests: **20 passed**;
- full module regression: **401 passed**;
- repository suite: **completed**;
- conceptual-model quality gate: **passed**;
- DuckDB materialization with knowledge-layer-core **0.29.1**: **completed**.

## AT900 delta

| Metric | 0.40.5 | 0.40.6 |
|---|---:|---:|
| Production constructor gaps | 30 | 3 |
| Constructor mappings (isolated source validation) | 247 | 259 |
| Constructor derivations (isolated source validation) | 432 | 453 |
| Data-model attribute mappings | 1,723 | 1,735 |
| Data-model attribute derivations | 1,940 | 1,961 |
| Workspace missing facts | 7,237 | 7,210 |

## Evidence resolved

The patch resolves only facts that are explicitly observable from AST and Java API semantics:

- method-local value identity, including locals declared before branch assignments;
- parameters of the exact containing lambda;
- jOOQ `Record.getValue(Field)` when the `Field` initializer exposes the projected name;
- import-proven `java.util.Collections.emptyMap/emptyList/emptySet`;
- same-class copy expressions whose class fields are explicit in the expression;
- `Optional<T>` unwrap methods on a receiver with an observed `Optional<T>` declaration.

Each emitted mapping/derivation retains resolution kind and source provenance.

## Remaining gaps

Exactly **3** constructor gaps remain in compact evidence and DuckDB. All are direct DAO calls returning the value supplied to `PprbProfileByUcpIdRs.profiles`. The source does not prove the DAO return-field contract, so the analyzer intentionally does not fabricate a mapping.

No AT900/UCP, package, class or field-name special case was introduced.
