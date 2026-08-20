# Статус тестирования — итерация 94 KLC

## Сфокусированные тесты

Результат: **14 passed, 0 failed**.

Проверены:

- workflow-context resolution предыдущей итерации;
- target candidate ranking;
- основной insertion-context contract;
- выбор SQL scope с исходной relation и колонкой;
- возврат target SQL files;
- честный `partial` при отсутствии exact propagation path;
- валидация обязательных аргументов;
- capability exposure.

## Реальный smoke

Artifact: неизменённый `datamart_profile_fl` DuckDB.

### BirthPlace → regionCode

1. `stg_epk_client_birthplace_snp.sql` — rank 1, `probable`;
2. `stg_epk_client_birthplace_hist.sql` — rank 2, `probable`;
3. `epk_client.sql` возвращён как target SQL и техническая альтернатива.

### Individual → countryresident

1. `stg_epk_client_individual_snp.sql` — rank 1;
2. исходная колонка `countryresident` наблюдается в выбранном scope;
3. target relation — `epk_client`.

## Не выполнялось

Полный KLC suite не запускался. Не менялись schema, ingestion, core evidence, SQL parser, lineage, data-model или topology. Изменён read-only query surface; он покрыт сфокусированными тестами и двумя реальными smoke-сценариями.
