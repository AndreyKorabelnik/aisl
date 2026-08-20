# Changed files — Analysis UI 2.0.0a51

## Runtime

- `src/analysis_ui/runtime/pipeline.py` — явные контракты однорепозиторных и workspace-мастеров; backend-валидация цели запуска.
- `src/analysis_ui/runtime/jobs.py` — repository-анализ стандартных мастеров с собственной материализацией Knowledge Layer.
- `src/analysis_ui/runtime/profiles.py` — описания профилей приведены к однорепозиторному контракту.

## Frontend

- `frontend/src/views/ProfileWizard.vue` — маршрутизация стандартных мастеров в однорепозиторную форму.
- `frontend/src/components/AnalysisForm.vue` — форма одного репозитория для модели данных, описания системы и хранения внешних данных.
- `frontend/src/components/WorkspaceForm.vue` — исключение однорепозиторных мастеров из workspace-профилей.
- `frontend/src/views/Home.vue` — отображение области запуска «Один репозиторий».
- `frontend/src/services/api.ts` — формирование repository job и проверка единственного найденного репозитория.
- `frontend/src/services/types.ts` — поля наименования и идентификатора системы для repository job.

## Contracts and documentation

- `docs/api/generic-v1.openapi.json` — версия API `2.0.0a51`.
- `docs/runtime/ARCHITECTURE.md` — разделение стандартных repository-мастеров и специальных workspace-сценариев.
- `docs/runtime/OPERATIONS.md` — актуальные операционные сценарии запуска.
- `docs/frontend/workspace-visible-sections.sha256` — обновлён визуальный контракт формы анализа.
- `README.md`, `VERSION`, `pyproject.toml`, `src/analysis_ui/__init__.py` — версия и описание релиза.
- `frontend/package.json`, `frontend/package-lock.json` — версия frontend `2.0.0-alpha.22`.

## Tests

- `tests/test_runtime_backend.py` — repository/workspace routing, запреты неверной цели, материализация и повторные запуски.
- `tests/test_revision_first_ui.py` — контракт однорепозиторного интерфейса.
- `tests/test_frontend_generic_migration.py` — исключение стандартных мастеров из workspace.
- `tests/test_module_baseline.py` — новая версия модуля.
