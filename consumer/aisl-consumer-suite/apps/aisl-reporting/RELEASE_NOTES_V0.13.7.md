# aisl-reporting 0.13.7

## Назначение

Версия гарантирует контроль наличия ER-диаграмм в сформированных отчётах модели данных и добавляет один безопасный корректирующий LLM-проход, когда основной renderer пропустил обязательную диаграмму.

## Мягкая ER-валидация

Для `data-model-report/v1`:

- `logical_only` и `physical_only` требуют минимум один непустой Mermaid-блок `erDiagram`;
- `logical_and_physical` требует два непустых ER-блока;
- `not_observed` не требует диаграммы;
- пустой блок, блок другого типа или один блок вместо двух возвращает warning `missing_required_er_diagram`;
- validation остаётся advisory и не удаляет сформированный отчёт.

## Корректирующий проход

`ModelRenderer` явно поддерживает correction pass, `FileRenderer` — нет.

Если ER отсутствует:

1. исходный отчёт сохраняется;
2. LLM получает только `er_correction_dataset/v1` с `logical_er`, `physical_er`, `observed_usage` и списком обязательных слоёв;
3. LLM обязана вернуть только раздел `ER-диаграммы`;
4. candidate нормализуется и повторно валидируется;
5. валидный раздел заменяет только ER-раздел отчёта;
6. исходная версия сохраняется как `report.before-er-correction.md`;
7. невалидная или упавшая коррекция отклоняется, исходный отчёт остаётся результатом с warning.

## Безопасность и доказательность

Correction dataset не содержит полного исходного кода и не даёт доступа к другим разделам отчёта. Physical ER разрешает только declared schema relationships; observed SQL/JOOQ/data-movement остаются отдельным слоем.

## Тесты

- compileall: passed;
- targeted validation/correction tests: 17 passed;
- full AISL Reporting: 77 passed, 16 skipped;
- skipped требуют внешних UCP/@900/Git artifacts.
