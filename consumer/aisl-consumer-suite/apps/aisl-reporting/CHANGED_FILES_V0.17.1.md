# Changed files — aisl-reporting 0.17.1

## Изменены

- `aisl_reporting/profiles/data_model_report/v1/builder.py`
  - компактная API-проекция полей, связей, PDM-таблиц, колонок и связей;
  - детерминированные лимиты по `detail_level`;
  - явные `selected_*_count` и `*_truncated`;
  - служебные UUID и пустые/default-поля не дублируются в report dataset.
- `tests/test_knowledge_api_reporting.py`
  - проверка компактного контракта и бюджета dataset.
- `aisl_reporting/version.py`, `pyproject.toml`, `README.md`.

## Новые

- `RELEASE_NOTES_V0.17.1.md`
- `TEST_RESULTS_V0.17.1.md`
- `CHANGED_FILES_V0.17.1.md`
