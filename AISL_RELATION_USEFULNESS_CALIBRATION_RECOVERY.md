# AISL relation usefulness calibration — recovery

Date: 2026-08-15
Status: RELATION_USEFULNESS_CALIBRATION_AND_PRODUCT_IDENTITY_BASELINE

## What changed

- `knowledge-layer-core 0.61.0a32`
  - keeps evidence-level relationship `confidence` unchanged;
  - publishes separate `basis.usefulness` for consumer actionability;
  - distinguishes `confirmed`, `strongly_supported`, `probable`, `ambiguity`, `unresolved`;
  - distinguishes exact observed SQL JOIN reuse from proposed/analog JOIN guidance;
  - preserves collection multiplicity and polymorphic concrete-target ambiguity;
  - canonicalizes KnowledgeProduct manifests before identity hashing by removing execution-local timestamps and local staging/cache paths, so identical semantic materialization inputs produce stable KnowledgeProduct `artifact_id` / `content_fingerprint`.
- `knowledge-integration 0.1.10`
  - `attribute-addition-plan/v1` profile version 12 consumes `basis.usefulness` separately from technical confidence;
  - no silent one-to-one reduction for collections and no silent subtype choice for polymorphic relationships.

No Core, Runner, Prepared Runtime, Knowledge API or KCP implementation changes in this block.

## Real calibration cases

- `Region.timeZone -> TimeZone`: exact observed SQL JOIN => useful classification `confirmed`.
- `BirthPlace.regionCode -> Region`: confirmed storage/key encoding + analog SQL but no exact current relationship JOIN => `strongly_supported` proposed JOIN with residual checks.
- `CustomerKnowledge.markers -> Marker`: confirmed collection storage semantics, cardinality many => `strongly_supported` collection navigation preserving row multiplicity.
- `Individual.identifications -> AbstractIdentification`: confirmed relationship but multiple observed concrete targets => `ambiguity`; consumer must not silently select a subtype.
- direct references with weaker SQL/storage representation evidence remain `probable` rather than being promoted.

## Determinism

Two real minimal Runner executions with the same plan/scope and the same five prior-revision KnowledgeProduct content fingerprints produced the same derived KnowledgeProduct `artifact_id` and `content_fingerprint`. Execution-result fingerprints may differ because execution timestamps/provenance differ; KnowledgeRevision identity remains execution-result based by current publication contract.

## Tests

- KLC full suite after final identity fix, with canonical sqlglot 30.13.0 on PYTHONPATH: 252 PASS, 8 SKIPPED.
- Previously failing identity-contract subset: 12/12 PASS.
- Knowledge Integration: 15/15 PASS.
- Workspace SQL catalog test with canonical sqlglot 30.13.0: PASS.
- Earlier consumer HTTP/publication acceptance in this block: PASS for calibrated classes through pinned Knowledge API.

## Important diagnostic

A KLC full-suite invocation without `sqlglot` on PYTHONPATH produced one workspace SQL catalog failure (251 PASS, 8 SKIPPED, 1 FAIL). The same test passes with the provided canonical `sqlglot 30.13.0` wheel; this is environment/dependency setup, not a code regression.

## Continuation

1. Do not rebuild a second relation/actionability mechanism. Reuse `basis.usefulness` owned by `data-model-attribute-extension-context`.
2. If continuing this block, run release packaging/representative publication only if further code changes are made; this recovery snapshot is already test-clean.
3. Return to product value: validate additional real attribute-extension tasks and only fix concrete knowledge/read gaps.
4. UCP 91 external DeepSeek blind run remains parked until the user explicitly resumes it.
