# Test results — Analysis UI 2.0.0a53

## Scope

Проверен локализованный контур нормализации URL и повторной публикации в Knowledge API.

## Results

- публикация с полным API URL — passed;
- публикация с корневым URL сервера — passed;
- retry с этапа publication и повторное использование готовых артефактов — passed.

Результат: **3 passed**.

## Additional validation

- Python `compileall`: passed.
- Generic OpenAPI version updated to `2.0.0a53`.
- Source manifest generation and verification: passed during packaging.
- ZIP integrity and clean-extraction smoke: passed during packaging.

## Environment note

В среде упаковки пакет `knowledge-assistant` отсутствовал. Публикационные тесты запускались с тестовой заглушкой только для импортируемых assistant-классов; код поставки и runtime-поведение Knowledge API не подменялись.

## Not run

Полная историческая регрессия и production frontend build не запускались: изменение локализовано в HTTP-клиенте публикации, frontend не менялся.
