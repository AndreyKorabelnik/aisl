# Test results — aisl-reporting 0.17.1

## Реальный E2E

- Источник: активная revision `ucp-datamart-pdm` с UCP, SQL и PDM.
- Dataset до исправления: `1038622` байта, строгая проверка отклоняла его.
- Dataset после исправления: `341952` байта по canonical JSON при лимите `500000`.
- Реальный Markdown: `41690` байт.
- Обязательные заголовки: все присутствуют.
- ER-диаграммы: 2 из 2, детерминированные.
- Report validation: `conforms=true`, предупреждений 0.
- Отчёт опубликован в Knowledge API revision `rev-c9c7a3315469cfe1814256f0`.
- `/reports`, `/reports/latest/content` и revision-specific content: HTTP 200; SHA-256 совпадает.

## Тесты

- Полный модульный прогон: **92 passed, 2 skipped, 0 failed**.
- Целевые data-model/ER/validation/policy проверки: **35 passed**.
- `compileall`: **OK**.
