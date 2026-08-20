# knowledge-layer-core 0.59.43

Legacy Cleanup Block 5.

- Replaced migration-era `knowledge_materialization_catalog/v2` with installed-runtime-only `knowledge_materialization_catalog/v3`.
- Removed migration metadata (`migration_source_stage`, `migration_priority`, `readiness`), planned migration lists, task routing and legacy umbrella decomposition from the current materialization contract.
- Preserved current evidence gaps as first-class materialization metadata.
- Materializations without a registered runtime handler remain visible as current unregistered contracts; no old implementation path is implied.
