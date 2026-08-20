# AISL System Description + FDP — change report

Date: 2026-08-15  
Status: **SYSTEM_DESCRIPTION_AND_FDP_AISL_BLOCK_COMPLETE**

## Changed modules

### knowledge-api 0.30.15

System Description:

- added `system-description-guidance/v1`;
- added `GET /api/knowledge/v1/systems/{system_id}/system-description/guidance`;
- compactly projects existing composition, technology, interface, integration, event, storage, journey, coverage and gap knowledge;
- reads enough canonical rows to retain exact KLC-owned section totals, while bounding LLM-facing presentation;
- preserves the detailed `/system-description/query` read for drill-down;
- `semantic_derivation = none`.

Foreign Data Persistence:

- added `foreign-data-persistence-guidance/v1`;
- added `GET /api/knowledge/v1/systems/{system_id}/foreign-data-persistence/guidance`;
- supports an optional token for scoped navigation;
- retains exact KLC path/case/storage summary counts;
- bounds path, case, storage-summary and evidence presentation;
- removes heavy raw-fact duplication from the compact projection;
- preserves canonical `/foreign-data-persistence/query` as the detailed drill-down surface;
- copies existing KLC statuses; does not infer a new same-data bridge or business FDP verdict;
- `semantic_derivation = none`.

### knowledge-integration 0.1.14

System Description:

- profile `system-description/v1` upgraded to profile v2;
- added capability-gated `get_system_description_context`;
- common “describe system” flow starts with the compact guidance read;
- existing detailed tools remain available for targeted follow-up.

Foreign Data Persistence:

- profile `foreign-data-persistence/v1` upgraded to profile v2;
- added capability-gated `get_fdp_context` with optional token;
- common FDP flow starts with the compact guidance read;
- `get_fdp_landscape` remains a detailed/raw drill-down tool;
- retrieval policy explicitly states that technical same-data confirmation is not business/legal foreign-data classification;
- tool catalog contract version advanced to v7.

### knowledge-control-plane 1.2.0a23

- fixed post-Runner output indexing so KCP does not recursively SHA/hash deep Core evidence payload shards;
- KCP indexes the official typed Core evidence descriptor and orchestration/materialization/publication artifacts;
- producer-owned evidence payload remains referenced by provenance instead of being re-inventoried by KCP;
- a real fresh System Description one-shot that previously stalled after Runner completion now reaches successful publication.

## Unchanged producer owners

No runtime code changed in:

- evidence-common 0.23.2;
- code-analyzer-core 0.44.23a5;
- static-analysis-runner 0.10.25;
- prepared-knowledge-runtime 0.1.0.post7;
- knowledge-layer-core 0.61.0a32;
- knowledge-reporting 0.18.0;
- aisl-contract 0.3.0b4.

No new analyzer, second producer, second materializer, compatibility adapter, dual read/write path or Gold-specific rule was introduced.

## Why these changes are generic

The consumer fixes are projections over stable typed KnowledgeProducts. They are driven by observed consumer payload fragmentation/volume, not by repository-specific names or known Gold answers.

The KCP fix restores ownership boundaries: Core/Runner own evidence payload/catalog details; KCP owns orchestration/publication artifact tracking. It is not a special case for AT900 or System Description.
