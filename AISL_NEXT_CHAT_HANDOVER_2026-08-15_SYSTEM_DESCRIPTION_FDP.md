# AISL next-chat handover — System Description + Foreign Data Persistence

Date: 2026-08-15  
Status: **SYSTEM_DESCRIPTION_AND_FDP_AISL_BLOCK_COMPLETE**

## Canonical architecture

```text
Formalized Sources
→ Core
→ Runner
→ KLC
→ knowledge_execution_result/v2 / PublicationCandidate
→ validation + atomic publication
════════ AISL publication boundary ════════
→ immutable KnowledgeRevision / typed KnowledgeProducts
→ Prepared Knowledge Runtime / Knowledge API
→ consumer-only Agent SDK / external agents
```

AISL Core Architecture remains formed. Current work expands product coverage and consumer ergonomics; it does not introduce a new semantic layer.

## What this block completed

### System Description

- current AT900 `client-profile` structural Gold reproduced;
- existing Core/KLC evidence and materialization were sufficient;
- added compact `system-description-guidance/v1` read;
- common LLM context reduced by ~87% while preserving exact KLC section totals;
- no business-purpose inference was added to Knowledge API.

### KCP lifecycle

- real fresh System Description runs exposed a reproducible post-Runner stall caused by recursive indexing/hashing of deep producer-owned Core payload shards;
- KCP 1.2.0a23 now indexes the official evidence descriptor and orchestration/publication artifacts, not the internal evidence payload tree;
- fresh real one-shot then completed and published successfully.

### Foreign Data Persistence

- current canonical persistence lineage reproduced without Core/Runner/KLC code changes;
- canonical result: 781 paths, 969 mechanical cases, 8 confirmed exact same-data cases;
- representative DEVICE_LINK and MNP/OPERATORID cases reproduced;
- added compact `foreign-data-persistence-guidance/v1` read;
- common-case payload reduced by 87–99% depending on scope;
- business/legal foreign-data classification remains explicitly unassigned.

## Current versions

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- prepared-knowledge-runtime 0.1.0.post7
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.14
- knowledge-api 0.30.15
- knowledge-reporting 0.18.0
- knowledge-control-plane 1.2.0a23
- aisl-contract 0.3.0b4

## Completed regression

- Knowledge API: 102/102 PASS (complete split 46/46 + 56/56)
- Knowledge Integration: 18/18 PASS
- Knowledge Control Plane: 95/95 PASS in clean environment
- Knowledge Layer Core: 252 PASS, 8 SKIPPED
- real fresh System Description publication: PASS
- real FDP publication through official Core reuse: PASS
- live compact consumer reads: PASS

## Important semantic boundaries

- Manual Gold is acceptance/reference only.
- System Description compact read does not assign business purpose or functional areas.
- FDP technical same-data confirmation is not equivalent to “foreign data” business/legal classification.
- Missing source-system evidence remains unresolved/null.
- No Core/Runner/KLC code changed for System Description or FDP semantics.
- No compatibility adapter, second producer or second materializer was introduced.

## Next recommended block

Reference Data / НСИ through AISL, unless the user changes priority.

Start with an audit of existing Core evidence, KLC `reference-data` materialization and current Knowledge API reads. Compare to Manual Gold structurally first. Do not create a new analyzer or change Core unless a missing observed fact is demonstrated.

## Parked scope

Do not resume automatically:

- UCP 91 independent external blind run;
- FI-002;
- vector/embedding retrieval inside AISL;
- portfolio topology;
- universal graph/EAV;
- agent memory/planning;
- compatibility cleanup without a proven architectural duplicate.
