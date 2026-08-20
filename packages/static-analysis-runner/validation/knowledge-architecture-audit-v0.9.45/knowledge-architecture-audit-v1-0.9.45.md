# Knowledge Architecture Audit v1

- Runner: `0.9.45`
- Схема: `knowledge_architecture_audit/v1`
- Fingerprint: `ef6f1b294a9983e9404bff1905bb8221d668b1c56300527d3f5e89672d756efc`
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
- **BLOCKED** `typed_evidence_contracts` — At least one required evidence schema is still only proposed or unknown.
- **BLOCKED** `core_runtime_publication` — At least one required typed artifact is not published by current runtime.
- **BLOCKED** `runner_artifact_registration` — Runner has no complete general typed evidence registry for at least one required Core artifact.
- **BLOCKED** `klc_materialization_runtime` — Target KLC materialization is declared but runtime implementation is not current.
- **BLOCKED** `legacy_semantic_routing_removed` — Current Task-based routes still carry legacy knowledge semantics.

### Обязательные evidence

- `java-type-structure-evidence`: observations=`current_observations_exist`, contract=`missing_proposed`, runtime=`not_implemented`, runner=`blocked_by_runtime_publication`

### Следующие действия

1. `define_typed_evidence_contract` — Define the complete uncapped typed contract for java-type-structure-evidence with provenance, coverage, diagnostics and content fingerprint.
2. `publish_typed_evidence_runtime` — Publish java-type-structure-evidence from its Core/external producer without Task-based semantic discovery.
3. `register_typed_artifact_in_runner` — Register java-type-structure-evidence by artifact_kind + schema_version in the Runner execution result.
4. `implement_klc_materialization` — Implement the target KLC materialization over typed evidence and publish coverage, diagnostics and provenance.
5. `run_scoped_parity` — Compare only the semantics of this knowledge type with the corresponding legacy bundle sections.
6. `remove_legacy_semantic_routes` — Remove relevant task_id routes and legacy bundle selection after scoped parity; do not keep a compatibility adapter.

### Текущие legacy routes

- `suite.capability-publication`: `task_id` → `successfully materialized KLC model capability`
- `suite.common-data-model-selection`: `task_id` → `typed artifacts and KLC model dependencies for decomposed data-model materializations`

## Ограничения

- The audit evaluates official declared contracts and current catalog mappings; it does not parse Core or KLC source code.
- Payload completeness cannot be proven before a typed evidence contract and runtime artifact exist.
- Actual repository source availability and per-run coverage are outside this architecture audit.
- Current business availability may rely on legacy mixed artifacts even when the target boundary is blocked.

Следующий шаг: `remove_specialized_Core_conceptual-model-evidence-sufficiency_command_then_define_java-type-structure-evidence/v1`
