# Test status — aisl-reporting 0.13.7

- compileall: passed;
- targeted ER validation and correction: 17 passed;
- full package suite: 77 passed, 16 skipped.

Проверены physical-only, logical-only, mixed model, entity-only ER, успешная коррекция, отклонение невалидной коррекции, сохранение исходного отчёта и отсутствие hard failure от report validation.

16 skipped относятся только к отсутствующим внешним UCP/@900/Git artifacts. Изменённые paths не пропущены.

Известное ограничение: validator проверяет число непустых ER-блоков, но не выполняет полный семантический разбор Mermaid-рёбер относительно dataset. Доказательная дисциплина обеспечивается ограниченным correction dataset и prompt; более строгая edge-level validation потребует стабильного machine-readable mapping Mermaid identifiers.

Wheel: `aisl_reporting-0.13.7-py3-none-any.whl`; SHA-256 `b159e818fa0d67973da64d007071a049a9940c43b5aa77c7d620b6d764c3c0d6`. Новый `er_correction.py` и изменённые runtime modules присутствуют в wheel.
