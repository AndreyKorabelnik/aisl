# knowledge-layer-core 0.59.47 test status

Status: PASS

- Affected KLC query/contract suite: 39 passed.
- Includes Consumer query surface, generic query layer, scope-neutral dependency, materialization contracts, cross-artifact mapping/workflow dependency, SQL knowledge layer, target-source query, and attribute-extension query.
- Real existing Prepared Knowledge smoke: relation materialization and SQL query context successfully read without rematerialization.
- Compileall: PASS.

Known limitation: these queries expose observed/materialized propagation facts; they do not infer a missing business target representation or synthesize SQL.
