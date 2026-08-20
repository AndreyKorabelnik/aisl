# Test status — knowledge-layer-core 0.59.30

- targeted interaction/value-flow/contract suite: **38 passed**.
- new generic regressions:
  - case-only HTTP path difference does not create a false match: PASS;
  - case-preserving suffix match reports `normalized_path` basis: PASS.
- real four-repository rematerialization from existing Core 0.44.16 evidence: PASS.
- real result: 3 interactions, 3 boundary interactions, 8 execution contexts, 17 diagnostics.
- compileall: PASS.

Known limitations intentionally unchanged:
- all three real matches remain `probable` because target-side address/service identity evidence is absent;
- one of six Manual Gold update/create ingress contexts remains an explicit upstream evidence gap;
- downstream field/value-flow richness is validated in dependent materializations/reporting checkpoints, not redefined by this path-normalization change.
