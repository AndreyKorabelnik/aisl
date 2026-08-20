# knowledge-layer-core 0.52.9

Версия 0.52.9 добавляет read-only определение SQL-точки, где новый атрибут целесообразно получить из системы-источника.

## Добавлено

- `KnowledgeLayerQuery.resolve_sql_attribute_insertion_context(...)`;
- capability `common.sql-attribute-insertion-context`;
- детерминированное ранжирование SQL scopes по уже материализованным фактам:
  - наблюдаемая исходная relation;
  - наблюдаемое исходное поле;
  - принадлежность target workflow;
  - точный каталог логической витрины;
  - прямое чтение physical-template источника;
  - существующие joins, projections и write observations;
  - source workflow contexts и их `main_table_name`;
- выдача основного варианта, альтернатив, target SQL files, evidence и diagnostics.

## Правила

- прямое чтение внешней physical-template relation имеет приоритет над совпадением только по технической stage-таблице;
- отсутствие полностью доказанного object-dependency пути не блокирует выдачу лучшего SQL scope;
- такой путь маркируется `probable` или `partial` и сопровождается diagnostic;
- KLC не меняет SQL и не создаёт patch;
- LLM остаётся владельцем итогового SQL и комментариев пользователю.

## Реальный результат

На `datamart_profile_fl`:

- для `BirthPlace` первым выбран `stg_epk_client_birthplace_snp.sql`, вторым — HIST-ветка;
- финальный `epk_client.sql` возвращается как target SQL и последующий этап, но не подменяет прямой источник;
- для `Individual.countryresident` первым выбран `stg_epk_client_individual_snp.sql`;
- таблица назначения `epk_client` определяется автоматически.

## Граница

Точный end-to-end relation dependency для wrapper-driven `runAndSaveSqlHdfs` в текущих фактах может отсутствовать. Resolver не фабрикует его и возвращает лучший вариант с комментарием.
