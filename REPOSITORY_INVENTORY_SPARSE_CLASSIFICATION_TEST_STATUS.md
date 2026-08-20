# Repository Inventory — Sparse Concept Classification Test Status

Date: 2026-08-16  
Status: **PASS**

Final relevant results:

- KLC sparse registry/materialization targeted set: **10/10 PASS**.
- knowledge-layer-core full regression: **257 PASS / 8 SKIP**.
- knowledge-control-plane full regression after canonical contract repin: **95/95 PASS**.
- Prepared Knowledge Runtime full suite: **10/10 PASS**.
- Knowledge API Repository Inventory affected tests: **2/2 PASS**.
- Fresh real gateway Runner → Core → KLC force-rebuild: **PASS**.
- Fresh real datamart Runner → Core → KLC force-rebuild: **PASS**.
- Machine semantic/structural sparse-vs-dense counterfactual acceptance: **PASS**.

Environment/setup failures were not counted as functional failures or PASS: the first materialization run lacked DuckDB in the session, and the first API test command omitted `knowledge_integration` from `PYTHONPATH`; both were rerun successfully with the canonical dependencies.

Final release gates:

- final versioned KLC full rerun (`0.61.0a36`): **257 PASS / 8 SKIP**.
- KCP pinned-bundle regression (`1.2.0a28`): **95/95 PASS**.
- all 9 runtime modules compile/import: **PASS**.
- changed KLC/KCP source JSON manifests: **PASS**.
- all 9 package `SOURCE_TREE_MANIFEST.sha256` contracts: **PASS** using each package's existing inclusion policy.
- KCP pinned bundle baseline: Core `0.44.23a7`, KLC `0.61.0a36`, Runner `0.10.27`; catalog SHA/fingerprints verified.
