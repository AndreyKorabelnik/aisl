# Test status — aisl-reporting 0.13.9

- compileall: passed;
- targeted SQL/Git/PDM contracts: 8 passed, 2 skipped;
- full package suite: 86 passed, 16 skipped.

Проверены:

- полный и детерминированный SQL source grouping;
- сохранение всех source names и field counts внутри групп;
- расширенные top/profile budgets SQL;
- полный и детерминированный Git changed-file group catalog;
- сводка всех непустых semantic delta types;
- корректная передача факта неполного delta artifact set;
- richness requirements SQL и Git prompts;
- отсутствие отдельного `pdm-report/v1` и использование `data-model-report/v1` для `physical_only`.

16 skipped относятся к отсутствующим внешним UCP/@900/Git artifacts. Два skipped в targeted run — существующие real Git fixture tests. Изменённые helper, prompt и contract paths проверены локальными тестами.

Известные ограничения:

- реальная LLM-регрессия качества выполняется отдельным следующим шагом;
- SQL Source Inventory намеренно не превращён в полный SQL Mart business report: он не придумывает target grain, методики расчёта и lineage, которых нет в его dataset;
- Git report не устанавливает downstream impact, migration/backfill/rollback и фактический test result без соответствующего evidence.

Wheel: `aisl_reporting-0.13.9-py3-none-any.whl`; SHA-256 `837fbb2902198422db1c2763df1fd55aaf9574a6bc1b4c95cc254472be9bbaea`.
