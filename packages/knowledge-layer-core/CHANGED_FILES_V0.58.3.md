# knowledge-layer-core 0.58.3

- `subject_knowledge_schema.py`: canonical subject-knowledge tables.
- `subject_knowledge_builder.py`: deterministic materialization from typed evidence.
- materialization runtime/contracts: handlers for `system-description` and `reference-data`.
- query/reporting/evidence surfaces: typed subject-record access without task fallback.
- suite builder: removed system-description/reference-data tasks; retained interface ingestion under `flow-lineage` only until Block 5B.
