# Test status — knowledge-layer-core 0.59.32

- targeted interaction/value-flow/materialization suite: **36 passed**.
- generic composed-boundary member-wire regression: PASS.
- real four-repository cross-repository-value-flow rematerialization: PASS.
- real transport edges: **46**.
- real composed-boundary member edges: **420**.
- real update/create `name.surname` source-local -> target-wire resolver: **probable_complete**, 3 steps; local serialization and boundary-composition steps confirmed, transport probable.
- compileall/import/package checks: performed during final packaging.

Known limitations intentionally unchanged:
- one of six Manual Gold update/create execution contexts remains an upstream evidence gap;
- system-interaction confidence policy remains unchanged;
- richer report selection still needs downstream validation; this KLC change only exposes the technical graph.
