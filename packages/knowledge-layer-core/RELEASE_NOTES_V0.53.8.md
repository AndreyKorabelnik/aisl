# knowledge-layer-core 0.53.8

Adds the read-only `knowledge_materialization_catalog/v1` and per-materialization `knowledge_materialization_contract/v1` contracts.

The catalog defines required and optional typed evidence inputs, produced knowledge models, capabilities, current implementation references and the four planned Core-to-KLC migrations. It also inventories the current KLC routes where `task_id` still selects artifact meaning or capabilities.

No ingestion, materialization, query or publication runtime was changed. The target semantic selector is `artifact_kind + schema_version`; task, suite and profile identifiers remain execution provenance only.
