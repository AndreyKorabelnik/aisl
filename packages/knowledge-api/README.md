# knowledge-api 0.19.2

Канонический API публикации и чтения типизированных знаний, произведённых единым knowledge execution-контуром.

API не запускает Core, Runner, KLC, отчёты или LLM. Он принимает только завершённый и проверяемый:

```text
knowledge_execution_result/v1
```

Из него API публикует неизменяемую ревизию системы, содержащую:

- сводку исполнения;
- исходный execution result;
- все типизированные knowledge artifacts;
- capabilities завершённых materializations;
- необязательный Markdown-отчёт.

Один общий DuckDB больше не является publication contract. Каждый доменный endpoint выбирает нужный типизированный артефакт по `model_kind` или capability.

## Import Producer publication bundle

For independent `aisl-producer` / `aisl-server` deployments, the preferred publication boundary is a self-contained bundle:

```bash
knowledge-api import \
  --bundle /path/to/job-....aisl.zip \
  --database outputs/knowledge-api/knowledge-api.sqlite3 \
  --artifact-store outputs/knowledge-api/artifact-store
```

The Server validates bundle/member SHA-256 identities, relocates Producer-local paths only for import-time validation, imports immutable bytes into its own content-addressed Artifact Store, and then creates the revision. No shared Producer filesystem or `KNOWLEDGE_API_ALLOWED_ROOTS` entry is required for bundle import.


## Запуск

```bash
knowledge-api serve \
  --database ./outputs/knowledge-api/knowledge-api.sqlite3 \
  --allowed-root ./outputs \
  --host 127.0.0.1 \
  --port 8080
```

Переменные окружения:

```text
KNOWLEDGE_API_DATABASE
KNOWLEDGE_API_ALLOWED_ROOTS
```

Каталог SQLite версии 0.15 и более ранних версий не мигрируется. Для 0.16 требуется новый каталог.

## Проверка результата исполнения

```bash
knowledge-api validate \
  --system-id ucp \
  --execution-result outputs/knowledge-execution/knowledge_execution_result.json
```

Проверяются:

- schema и fingerprint execution result;
- завершённость всех execution nodes и materializations;
- запрещённые fallback/dual-write политики;
- точное соответствие knowledge artifacts и capabilities результатам materializations;
- manifest и DuckDB каждого knowledge artifact;
- разрешённые корни файлов;
- возможность выполнить типизированный query для известных моделей.

Проверка не изменяет SQLite-каталог.

## Публикация

```bash
knowledge-api publish \
  --system-id ucp \
  --display-name "Единый профиль клиента" \
  --description "UCP knowledge" \
  --execution-result outputs/knowledge-execution/knowledge_execution_result.json \
  --label data-model
```

CLI вычисляет file URI, SHA-256, размер и media type. Система создаётся только после успешной проверки. `publish` не изменяет метаданные уже существующей системы.

Дополнительные параметры:

- `--dry-run` — проверить и показать действия без публикации;
- `--no-activate` — создать неактивную ревизию;
- `--format json` — машинный формат.

Флаги `--knowledge-layer` и `--source-manifest` удалены.

Reporting is not part of revision publication. Presentation artifacts are produced by independent consumers such as `aisl-reporting` from a pinned published revision; they do not change AISL revision identity.

## Ревизии и типизированные артефакты

```http
GET /api/knowledge/v1/systems/{system_id}/revisions
GET /api/knowledge/v1/systems/{system_id}/knowledge-artifacts
GET /api/knowledge/v1/systems/{system_id}/knowledge-artifacts/{artifact_id}
GET /api/knowledge/v1/systems/{system_id}/capabilities
```

Все endpoints принимают необязательный `revision_id`; без него используется активная ревизия.

## Модель данных

```http
GET /api/knowledge/v1/systems/{system_id}/data-model/tables
GET /api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}
GET /api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}/relationships/{relationship_id}
GET /api/knowledge/v1/systems/{system_id}/coverage
```

Эти endpoints читают только `effective-data-model/v1`. Объявленная модель, физическая модель и соответствие не смешиваются внутри API.

## Контекст добавления атрибута в витрину

```http
GET /api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-context
GET /api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-guidance
```

`attribute-extension-context` — полный canonical read typed artifact `data-model-attribute-extension-context/v1`, уже материализованного KLC. `attribute-extension-guidance` — компактная consumer projection того же ответа: она поднимает наверх KLC-owned `usefulness`, relation/JOIN evidence, key/reference expressions, storage observations, residual checks и gaps, ограничивая тяжёлые коллекции с явным truncation metadata.

Оба маршрута используют уже опубликованное knowledge. API не классифицирует связи, не сопоставляет выражения ключей, не выбирает JOIN predicate и не генерирует SQL. Поддерживаются точные фильтры `source_type`, `source_field`, `target_type`, `join_method`, `confidence`, `sql_generation_status` и навигационный `search`. Неустановленные или полиморфные физические JOIN остаются явными gaps/ambiguity; compact projection не повышает confidence.

## Физическая модель

```http
GET /api/knowledge/v1/systems/{system_id}/physical-model
GET /api/knowledge/v1/systems/{system_id}/physical-model/tables
GET /api/knowledge/v1/systems/{system_id}/physical-model/tables/{table_id}
GET /api/knowledge/v1/systems/{system_id}/physical-model/columns
GET /api/knowledge/v1/systems/{system_id}/physical-model/keys
GET /api/knowledge/v1/systems/{system_id}/physical-model/relationships
GET /api/knowledge/v1/systems/{system_id}/physical-model/gaps
```

Маршруты читают artifact с `model_kind=physical-data-model`. Роли SQL read/write из PDM не выводятся.

## SQL

SQL endpoints выбирают typed artifact детерминированно:

- `workspace-sql-catalog/v1` является каноническим для workspace revision;
- `knowledge_layer_sql/v2` используется для revision без workspace composition;
- несколько артефактов одного канонического model kind остаются ошибкой ambiguity;
- выбор не использует legacy bundle или скрытый fallback.

Поддерживаемые маршруты:

```http
GET  /api/knowledge/v1/systems/{system_id}/sql/relations
GET  /api/knowledge/v1/systems/{system_id}/sql/source-inventory
GET  /api/knowledge/v1/systems/{system_id}/sql/source-inventory.jsonl
GET  /api/knowledge/v1/systems/{system_id}/sql/target-column-lineage
GET  /api/knowledge/v1/systems/{system_id}/sql/field-calculation
GET  /api/knowledge/v1/systems/{system_id}/sql/target-candidates
POST /api/knowledge/v1/systems/{system_id}/sql/attribute-insertion-context
GET  /api/knowledge/v1/systems/{system_id}/sql/column-usages/{sql_column_usage_id}
```

`target-column-lineage` возвращает канонические рекурсивные lineage paths из KLC (`sql-target-column-lineage/v1`), включая transformation path, resolution statuses и scoped gaps. Поддерживаются точные фильтры `target_relation`, `target_column`, `repo_id` и `lineage_status`; API не восстанавливает lineage самостоятельно.

Отсутствие соответствующего knowledge artifact возвращается как явная ошибка, без поиска старого bundle или `sql-target-source-mapping`.

## Администрирование

```bash
knowledge-api system list
knowledge-api system show --system-id ucp
knowledge-api system update --system-id ucp --metadata owner=customer-data
knowledge-api revision list --system-id ucp
knowledge-api revision activate --system-id ucp --revision-id rev-...
knowledge-api system delete --system-id ucp --yes
```

## Публичный контракт

Базовый prefix:

```text
/api/knowledge/v1
```

OpenAPI:

```text
schemas/knowledge-v1.openapi.json
```

## Code-declared data model

A prepared revision containing `code-declared-data-model/v1` can be searched without rebuilding knowledge:

- `GET /api/knowledge/v1/systems/{system_id}/data-model/declared-objects?revision_id=...&search=...`
- `GET /api/knowledge/v1/systems/{system_id}/data-model/declared-objects/{object_id}?revision_id=...`

This surface exposes declared types, effective inherited fields, declared relationships, documentation, source references and provenance. It does **not** infer storage joins or replace `/data-model/attribute-extension-context`; the latter remains the KLC-owned source for JOIN/storage/SQL semantics.

## System Interactions read surface (0.22.0)

Prepared revisions can expose KLC-owned System Interactions knowledge through revision-bound endpoints under `/api/knowledge/v1/systems/{system_id}/interactions`: summary, boundaries, execution contexts, field contracts, diagnostics and optional repository coverage. Each endpoint is enabled only by the corresponding published capability; the API does not infer missing interaction knowledge or fall back across knowledge artifact families.

## System Description read surface (0.23.0)

A prepared revision that publishes `common.system-description` can be queried through `POST /api/knowledge/v1/systems/{system_id}/system-description/query`. The endpoint delegates to the KLC-owned reporting query facade and exposes scope overview, repository composition, declared technologies, interfaces, integrations, events, observed storage targets, coverage, gaps and representative journeys. Knowledge API does not infer business purpose, runtime topology, table relationships or source-of-truth semantics, and it does not fall back to other artifact families when System Description knowledge is unavailable.
