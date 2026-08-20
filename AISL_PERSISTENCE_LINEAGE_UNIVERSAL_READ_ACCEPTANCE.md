# AISL persistence-lineage universal read — acceptance

Date: 2026-08-15
Status: PASS WITH EXPLICIT P1 MAPPING INPUT GAP

## A. Positive real `maps_to` investigation

Observed:
- current `logical-physical-mapping` requires `java-persistence-mapping-evidence/v1`;
- the available real UCP/TSA/AT900/gateway/sbpr Java inputs contain no JPA/Jakarta persistence annotations matching that contract;
- AT900 contains jOOQ generated physical-schema classes and confirmed persistence lineage, which are different evidence semantics.

Acceptance verdict: **NO REPRESENTATIVE POSITIVE INPUT AVAILABLE**.

No JPA mapping was synthesized from names, jOOQ classes, SQL usage, or persistence lineage. This remains an explicit evidence/input gap, not a framework PASS/failure claim for positive `maps_to`.

## B. 91-attribute consumer validation checkpoint

The pre-rerun Manual Gold comparison baseline was 12/29 accepted positive matches (41.4% recall) and 12/26 accepted framework positives (46.2% precision). The current canonical runtime already contains the planned deterministic read mechanisms: match evidence, deterministic lexical score/basis, binding summary, and explicit `all_declared_types` scope expansion.

A fresh real UCP prepared code-declared model was built. For 12 representative prior miss cases whose exact Gold technical field token is known, deterministic exact retrieval found 12/12 targets; 10/12 were rank #1. Five require explicit expansion to `all_declared_types`.

This does **not** claim a new full 91-attribute external-agent score: no external LLM/agent provider is embedded in the canonical framework run performed here. The result establishes that these representative observed facts and exact read paths are available; remaining synonym/translation/business-semantic planning belongs to agent retrieval/reasoning unless a future test proves a deterministic AISL gap.

## C. Real AT900 producer → publication → consumer-only read

Formalized source: real AT900 `client-profile` repository.

Official Core persistence-lineage evidence:
- source files: 1038
- source-to-storage lineages: 529
- storage-to-access lineages: 252
- persistent writes: 138
- storage-lineage gaps: 1155
- stored-field mappings: 237

Official Runner output:
- schema: `knowledge_execution_result/v2`
- status: completed
- product artifact: `knowledge_artifact_59bbfd7034339e97adab`
- model kind: `persistence-lineage`
- schema: `persistence-lineage/v1`
- capabilities: `workspace.fdp-paths`, `workspace.persistence-lineage`

Official Knowledge API publication:
- system: `aisl-real-at900-persistence`
- revision: `rev-748e1f231c35d6186f988e24`

Consumer-only exact item read:
- item kind: `source_to_storage_lineage`
- local ID: `source_to_storage_lineage_000108`
- source payload: `SyncPushDeviceRequest`
- source field: `clientId`
- storage target: `DEVICE_LINK`
- storage field: `CLIENT_ID`
- lineage status: `confirmed`
- evidence maturity: `confirmed`
- source evidence: `DeviceLinkServiceImpl.java`, observed lines 193–237
- projection status: `available`
- correspondences: `unsupported`
- item-level coverage: `not_available`

The consumer-side API process was executed without Core, Runner, or KLC on its import path. It read the already published product only.

## D. Real negative/gap acceptance

Real item: `storage_lineage_gap_000230`.

Projection result:
- item available;
- issue kind: `missing_information`;
- gap kind: `dao_entity_type_unknown`;
- source inspection required: true;
- source inspection request IDs preserved;
- no guessed storage/entity relation;
- correspondences remain unsupported.

## E. Test results before release packaging

- knowledge-layer-core full: **247 PASS, 8 SKIPPED**
- prepared-knowledge-runtime full: **7 PASS**
- knowledge-api full: **92 PASS**
- knowledge-integration full: **15 PASS**
- combined affected contract tests: **11 PASS**
- compile/import changed modules: **PASS**
- official real Core → Runner → KLC → Knowledge API publication: **PASS**
- consumer-only confirmed exact read: **PASS**
- consumer-only real gap read: **PASS**

A prior API command exceeded its external execution timeout after tests had finished; the persisted pytest log contains the terminal result `92 passed in 32.23s`. It is classified as command-wrapper timeout, not functional test failure.
