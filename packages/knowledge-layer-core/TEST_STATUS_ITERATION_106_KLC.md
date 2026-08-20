# Статус тестирования — итерация 106 KLC

## Сфокусированные тесты

Результат: **32 passed, 0 failed**.

Проверены:

- typed materialization `physical-model/v1`;
- таблицы, колонки, ключи, связи и gaps;
- полная и partial coverage;
- manifest, порядок fact shards, SHA-256, размеры и content fingerprint;
- source-id consistency;
- orphan references и duplicate IDs;
- атомарная публикация и запрет перезаписи при `replace=false`;
- существующие contracts и infrastructure boundaries KLC.

## Реальный smoke

Источник: `PDM_B2C_restored`, модель `Модель ЕПКАП B2C`.

Материализовано:

- 522 физические таблицы;
- 11 940 колонок;
- 498 ключей;
- 370 связей;
- 0 gaps.

Все 370 связей имеют `resolution_status=resolved`. Orphan references и duplicate fact IDs отсутствуют. Сборка завершилась со статусом `complete`.

## Не выполнялось

Полный KLC suite не запускался. Общий data-model ingestion, SQL ingestion, topology и lineage не менялись. Изменён только новый самостоятельный PDM materialization contour; он покрыт узкими контрактными тестами и реальным smoke.
