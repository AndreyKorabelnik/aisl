# Knowledge Architecture Audit v1

- Runner: `0.9.51`
- Схема: `knowledge_architecture_audit/v1`
- Fingerprint: `0863d81128afc22bd25f383a97d5e0d35307f6bb366e1be3e655b7cbd95d8af1`
- Влияние на исполнение: `none`

## Итог

- Проверено знаний: **3**
- Полностью готовы по целевой границе: **3**
- Доступны через текущую систему, но требуют миграции: **0**
- Только запланированы и заблокированы: **0**

## Модель данных, объявленная в коде (`code-declared-data-model`)

- Целевой статус: `target_ready`
- Materialization: `code-declared-data-model`
- Lifecycle: `current_typed_input`
- Текущая бизнес-доступность: `current_typed`

### Проверки готовности

- **PASS** `knowledge_contract` — Knowledge type and KLC materialization requirements are declared in official catalogs.
- **PASS** `required_source_observations` — Required source observations are mapped to current producers.
- **PASS** `typed_evidence_contracts` — All required evidence schemas are defined.
- **PASS** `core_runtime_publication` — All required evidence artifacts are published by current runtime.
- **PASS** `runner_artifact_registration` — Required Core evidence is registered by Runner.
- **PASS** `klc_materialization_runtime` — KLC materialization is registered behind the generic knowledge_materialization_runtime/v1 entrypoint.
- **PASS** `legacy_semantic_routing_removed` — No relevant task_id semantic routes remain.

### Обязательные evidence

- `java-type-structure-evidence`: observations=`current_observations_exist`, contract=`defined_current`, runtime=`current`, runner=`current`

### Следующие действия


## Физическая модель данных (`physical-data-model`)

- Целевой статус: `target_ready`
- Materialization: `physical-model`
- Lifecycle: `current_typed_input`
- Текущая бизнес-доступность: `current_typed`

### Проверки готовности

- **PASS** `knowledge_contract` — Knowledge type and KLC materialization requirements are declared in official catalogs.
- **PASS** `required_source_observations` — Required source observations are mapped to current producers.
- **PASS** `typed_evidence_contracts` — All required evidence schemas are defined.
- **PASS** `core_runtime_publication` — All required evidence artifacts are published by current runtime.
- **PASS** `runner_artifact_registration` — Required Core evidence is registered by Runner.
- **PASS** `klc_materialization_runtime` — KLC materialization is registered behind the generic knowledge_materialization_runtime/v1 entrypoint.
- **PASS** `legacy_semantic_routing_removed` — No relevant task_id semantic routes remain.

### Обязательные evidence

- `physical-model`: observations=`not_core_stage_based`, contract=`defined_current`, runtime=`current`, runner=`input_registered_outside_core_analyzer_registry`

### Следующие действия


## Логико-физическое соответствие (`logical-physical-mapping`)

- Целевой статус: `target_ready`
- Materialization: `logical-physical-mapping`
- Lifecycle: `current_typed_input`
- Текущая бизнес-доступность: `current_typed`

### Проверки готовности

- **PASS** `knowledge_contract` — Knowledge type and KLC materialization requirements are declared in official catalogs.
- **PASS** `required_source_observations` — Required source observations are mapped to current producers.
- **PASS** `typed_evidence_contracts` — All required evidence schemas are defined.
- **PASS** `core_runtime_publication` — All required evidence artifacts are published by current runtime.
- **PASS** `runner_artifact_registration` — Required Core evidence is registered by Runner.
- **PASS** `klc_materialization_runtime` — KLC materialization is registered behind the generic knowledge_materialization_runtime/v1 entrypoint.
- **PASS** `legacy_semantic_routing_removed` — No relevant task_id semantic routes remain.

### Обязательные evidence

- `java-persistence-mapping-evidence`: observations=`current_observations_exist`, contract=`defined_current`, runtime=`current`, runner=`current`

### Следующие действия


## Ограничения

- The audit evaluates official declared contracts and current catalog mappings; it does not parse Core or KLC source code.
- Payload completeness cannot be proven before a typed evidence contract and runtime artifact exist.
- Actual repository source availability and per-run coverage are outside this architecture audit.
- Current business availability may rely on legacy mixed artifacts even when the target boundary is blocked.

Следующий шаг: `next_independent_evidence_and_materializer`
