from __future__ import annotations

from knowledge_control_plane.api.generic_v1.models import (
    PageMeta,
    ScenarioDefinition,
    ScenarioListResponse,
    ScenarioParameter,
    ScenarioSourceMode,
)

from .errors import ResourceNotFound


_PLATFORM_SCENARIOS = (
    ScenarioDefinition(
        scenario_id="build-repository-inventory-v1",
        name="Технический паспорт репозитория",
        knowledge_profile_id="repository-inventory-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/build-repository-inventory/v1",
        description="Построить bounded repository inventory: состав, технологии, концепты, inputs/outputs, coverage, novelty и diagnostics без обязательного deep-analysis.",
    ),
    ScenarioDefinition(
        scenario_id="build-data-model-v1",
        name="Модель данных из кода",
        knowledge_profile_id="data-model-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/build-data-model/v1",
        description="Построить reusable logical code-declared data model и открыть grounded chat.",
        assistant_profile_id="data-model/v1",
    ),
    ScenarioDefinition(
        scenario_id="build-effective-data-model-v1",
        name="Модель данных АС",
        knowledge_profile_id="effective-data-model-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/build-effective-data-model/v1",
        description="Построить effective data model: модель из кода + физическая модель + доказанные логико-физические соответствия.",
        parameters=[
            ScenarioParameter(
                name="physical_model_path",
                value_type="path",
                required=True,
                description="Физическая модель данных (например PowerDesigner PDM) для таблиц, колонок, ключей и связей.",
            )
        ],
    ),
    ScenarioDefinition(
        scenario_id="build-reference-data-v1",
        name="Собственные НСИ / справочные данные",
        knowledge_profile_id="reference-data-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/build-reference-data/v1",
        description="Построить reference-data context и подготовить отчёт/чат.",
        assistant_profile_id="reference-data/v1",
    ),
    ScenarioDefinition(
        scenario_id="analyze-foreign-data-persistence-v1",
        name="Хранение внешних данных / FDP",
        knowledge_profile_id="foreign-data-persistence-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/foreign-data-persistence/v1",
        description="Построить persistence lineage и подготовить FDP knowledge.",
        assistant_profile_id="foreign-data-persistence/v1",
    ),
    ScenarioDefinition(
        scenario_id="analyze-observed-storage-usage-v1",
        name="Наблюдаемое использование хранилищ",
        knowledge_profile_id="observed-storage-usage-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/observed-storage-usage/v1",
        description="Построить observed storage usage и отчёт.",
    ),
    ScenarioDefinition(
        scenario_id="analyze-sql-source-inventory-v1",
        name="SQL Source Inventory",
        knowledge_profile_id="sql-source-inventory-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/sql-source-inventory/v1",
        description="Построить SQL Source Inventory knowledge.",
    ),
    ScenarioDefinition(
        scenario_id="reconstruct-s2t-v1",
        name="S2T по коду витрины и PDM",
        knowledge_profile_id="s2t-reconstruction-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/s2t-reconstruction/v1",
        description="Построить S2T knowledge только по SQL-коду витрины и предоставленной физической модели данных.",
        parameters=[
            ScenarioParameter(
                name="physical_model_path",
                value_type="path",
                required=True,
                description="PowerDesigner PDM целевой физической модели.",
            )
        ],
    ),
    ScenarioDefinition(
        scenario_id="analyze-sql-change-v1",
        name="Расчёт поля и изменение SQL-витрины",
        knowledge_profile_id="sql-source-inventory-v1",
        source_mode=ScenarioSourceMode.REPOSITORY,
        version="v1",
        source_path="builtin:scenario/sql-change-analysis/v1",
        description="Использовать тот же SQL knowledge для field calculation/lineage/change analysis.",
        parameters=[
            ScenarioParameter(name="target_relation", value_type="string", required=True, description="Целевая физическая таблица."),
            ScenarioParameter(name="target_column", value_type="string", required=True, description="Целевая колонка."),
            ScenarioParameter(name="repo_id", value_type="string", required=False, description="Ограничить результат репозиторием."),
            ScenarioParameter(name="source_relation", value_type="string", required=False, description="Предполагаемая таблица-источник нового атрибута."),
            ScenarioParameter(name="source_column", value_type="string", required=False, description="Предполагаемая колонка-источник."),
            ScenarioParameter(name="business_entity", value_type="string", required=False, description="Бизнес-сущность для поиска кандидатов назначения."),
        ],
    ),
    ScenarioDefinition(
        scenario_id="compose-workspace-sql-catalog-v1",
        name="Workspace SQL Catalog",
        knowledge_profile_id="workspace-sql-catalog-v1",
        source_mode=ScenarioSourceMode.KNOWLEDGE_REVISIONS,
        version="v1",
        source_path="builtin:scenario/workspace-sql-catalog/v1",
        description="Собрать workspace SQL catalog из published revisions без source analysis.",
    ),
    ScenarioDefinition(
        scenario_id="extend-data-model-attribute-v1",
        name="Расширение модели данных и витрины",
        knowledge_profile_id="data-model-attribute-extension-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/data-model-attribute-extension/v1",
        description="Построить UCP + SQL + PDM knowledge для последующей модификации витрины.",
        parameters=[
            ScenarioParameter(
                name="physical_model_path",
                value_type="path",
                required=True,
                description="PowerDesigner PDM для физического контекста целевой модели.",
            )
        ],
        assistant_profile_id="attribute-addition-plan/v1",
    ),
    ScenarioDefinition(
        scenario_id="describe-system-v1",
        name="Описание системы",
        knowledge_profile_id="system-description-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/system-description/v1",
        description="Построить technical system description knowledge.",
        assistant_profile_id="system-description/v1",
    ),
    ScenarioDefinition(
        scenario_id="analyze-system-interactions-v1",
        name="Межсистемные взаимодействия",
        knowledge_profile_id="system-interactions-v1",
        source_mode=ScenarioSourceMode.REPOSITORIES,
        version="v1",
        source_path="builtin:scenario/system-interactions/v1",
        description="Построить interaction knowledge.",
        assistant_profile_id="system-interactions/v1",
    ),
)


class ScenarioService:
    """Control-plane registry for how users run reusable Knowledge Profiles."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._scenarios = {item.scenario_id: item for item in _PLATFORM_SCENARIOS}

    def all(self) -> list[ScenarioDefinition]:
        return list(self._scenarios.values())

    def list(self, *, offset: int, limit: int, search: str | None = None) -> ScenarioListResponse:
        items = self.all()
        if search:
            needle = search.casefold()
            items = [
                item
                for item in items
                if needle in item.scenario_id.casefold()
                or needle in item.name.casefold()
                or needle in (item.description or "").casefold()
            ]
        return ScenarioListResponse(
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )

    def get(self, scenario_id: str) -> ScenarioDefinition:
        scenario = self._scenarios.get(scenario_id)
        if scenario is None:
            raise ResourceNotFound("scenario", scenario_id)
        return scenario
