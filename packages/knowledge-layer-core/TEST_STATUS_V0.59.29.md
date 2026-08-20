# Test status — knowledge-layer-core 0.59.29

- targeted interaction + downstream value-flow tests: **15 passed**.
- generic new acceptance:
  - typed `local_call_chain_candidates` -> execution context: PASS;
  - two helper-composed call sites -> one boundary + two contexts: PASS.
- real four-repository rematerialization from existing Core 0.44.16 evidence: PASS.
- dependent interaction-field-contract materialization: PASS, 46 contracts.
- dependent cross-repository-value-flow materialization: PASS.
- compileall/import/package integrity: recorded during final packaging.

Known limitation: one of six Manual Gold update/create ingress contexts remains unresolved because the required controller->service call edge is absent from the typed boundary evidence used by this materialization.
