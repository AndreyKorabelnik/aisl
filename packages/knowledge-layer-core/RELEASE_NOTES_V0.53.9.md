# knowledge-layer-core 0.53.9 — data-model knowledge decomposition

- upgraded the read-only catalog to `knowledge_materialization_catalog/v2` and `knowledge_materialization_contract/v2`;
- added explicit KLC model dependencies alongside typed evidence inputs;
- removed planned `conceptual-data-model` as an undifferentiated target;
- added `code-declared-data-model`, `logical-physical-mapping`, `observed-storage-usage` and composite `effective-data-model` materializations;
- retained `physical-model` and `sql-analysis` as separate knowledge sources;
- added deterministic routing of 27 sections from legacy `code_conceptual_model/v2`;
- runtime ingestion, materialization, queries and UI are unchanged.
