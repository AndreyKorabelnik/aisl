# Test status — aisl-reporting 0.13.8

- compileall: passed;
- targeted contracts for rich reports: 17 passed;
- full package suite: 81 passed, 16 skipped.

Проверены:

- сохранение всех declared relationships при каталоге до 30;
- детерминированный detail-level budget для больших каталогов;
- отдельные бюджеты declared relationships и observed JOIN;
- расширенные journeys/interactions/field-contract limits;
- расширенные candidate и usage budgets НСИ;
- обязательные требования насыщенности в четырёх renderer prompts;
- сохранение приложений A–C после переработки основной части отчётов.

16 skipped относятся к отсутствующим внешним UCP/@900/Git artifacts. Изменённые paths не пропущены.

Известные ограничения:

- реальное сравнительное LLM-формирование отчётов будет выполнено отдельной регрессией после обновления оставшихся профилей;
- очень большие каталоги остаются bounded и сопровождаются явной metadata о полноте/политике выборки;
- версия не добавляет новые evidence и не меняет maturity существующих наблюдений.

Wheel: `aisl_reporting-0.13.8-py3-none-any.whl`; SHA-256 `7c54cda7cbb19471a509e4318a3d42410fea3d881f19dd9c09fb2a0946bed456`.
