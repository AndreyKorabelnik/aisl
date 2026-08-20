# Test status — aisl-reporting 0.14.1

## Выполнено

- `python -m compileall -q aisl_reporting tests`: passed;
- targeted suite: 26 passed;
- full package suite: 92 passed, 16 skipped;
- source manifest validation: passed;
- clean ZIP extraction and compileall: passed;
- clean ZIP full package suite: passed;
- wheel build with `pip wheel --no-deps --no-build-isolation`: passed;
- installed wheel version/resource smoke: passed.

## Что проверено

- безопасные Mermaid identifiers для qualified table/entity names;
- безопасные type/attribute tokens;
- очистка кавычек, pipe, backslash и multiline labels;
- declared FK публикуются только в physical ER;
- observed SQL/JOOQ relations публикуются отдельно;
- PK/FK flags формируются из dataset;
- entity-only ER поддерживается;
- заменяется только раздел `## ER-диаграммы`;
- остальные разделы отчёта сохраняются;
- deterministic generator неприменим к другим профилям;
- correction pass не вызывается при успешно построенной deterministic ER;
- correction pass сохраняется как fallback.

## Skipped

16 прежних тестов требуют внешних UCP/@900/Git artifacts. Они не объявлены пройденными.

## Известные ограничения

- проверка реального отображения SVG в браузере относится к Analysis UI и выполняется отдельной итерацией;
- Reporting гарантирует детерминированный Mermaid source, но не управляет тем, был ли пересобран frontend Analysis UI;
- semantic edge-level verification выполняется на уровне источника dataset; отдельный Mermaid parser не встраивается в Python runtime.
