# Knowledge Architecture Audit v1

- Runner: `0.9.46`
- Схема: `knowledge_architecture_audit/v1`
- Fingerprint: `bd052c8fa690cf0b551e044cbf2f78fc7a75266be132f676df8df07f5c9c0a38`
- Влияние на исполнение: `none`

## Итог

- Проверено знаний: **1**
- Полностью готовы по целевой границе: **0**
- Доступны через текущую систему, но требуют миграции: **1**
- Только запланированы и заблокированы: **0**

## Модель данных, объявленная в коде (`code-declared-data-model`)

- Целевой статус: `current_business_available_target_migration_required`
- Materialization: `code-declared-data-model`
- Lifecycle: `planned_core_to_klc_migration`
- Текущая бизнес-доступность: `current_legacy`

### Проверки готовности

- **PASS** `knowledge_contract` — Knowledge type and KLC materialization requirements are declared in official catalogs.
- **PASS** `required_source_observations` — Required source observations are mapped to current producers.
- **PASS** `typed_evidence_contracts` — All required evidence schemas are defined.
- **PASS** `core_runtime_publication` — All required evidence artifacts are published by current runtime.
- **PASS** `runner_artifact_registration` — Required Core evidence is registered by Runner.
- **BLOCKED** `klc_materialization_runtime` — Target KLC materialization is declared but runtime implementation is not current.
- **BLOCKED** `legacy_semantic_routing_removed` — Current Task-based routes still carry legacy knowledge semantics.

### Обязательные evidence

- `java-type-structure-evidence`: observations=`current_observations_exist`, contract=`defined_current`, runtime=`current`, runner=`current`

### Следующие действия

1. `implement_klc_materialization` — Implement the target KLC materialization over typed evidence and publish coverage, diagnostics and provenance.
2. `run_scoped_parity` — Compare only the semantics of this knowledge type with the corresponding legacy bundle sections.
3. `remove_legacy_semantic_routes` — Remove relevant task_id routes and legacy bundle selection after scoped parity; do not keep a compatibility adapter.

### Текущие legacy routes

- `suite.capability-publication`: `task_id` → `successfully materialized KLC model capability`
- `suite.common-data-model-selection`: `task_id` → `typed artifacts and KLC model dependencies for decomposed data-model materializations`

## Ограничения

- The audit evaluates official declared contracts and current catalog mappings; it does not parse Core or KLC source code.
- Payload completeness cannot be proven before a typed evidence contract and runtime artifact exist.
- Actual repository source availability and per-run coverage are outside this architecture audit.
- Current business availability may rely on legacy mixed artifacts even when the target boundary is blocked.

Следующий шаг: `implement_KLC_code-declared-data-model_materialization_over_java-type-structure-evidence/v1`
