# knowledge-layer-core 0.52.8

Версия 0.52.8 завершает контекстное разрешение SQL-файлов по доказанным workflow bindings.

## Изменено

- контекстный resolver теперь может не только сужать заранее найденных кандидатов, но и повторно выполнить точное repository-local сопоставление после подстановки известных workflow-параметров;
- неизвестный корневой placeholder не мешает использовать последующие известные параметры;
- ссылка вида `$datamart_dir/wf/dml/${$main_table_name}/${$main_table_name}.sql` разрешается в конкретный SQL только внутри workflow, где доказано значение `main_table_name`;
- unresolved static references сохраняются в графе и могут быть разрешены позднее только при наличии контекстного binding;
- глобальное сопоставление по одному имени файла не добавлено.

## Реальный результат

Для workflow `b2c_profile_fl_epk_client.yaml` на неизменённом `datamart_profile_fl` доказательно разрешены:

1. `.../wf/dml/epk_client/prep_src.sql`;
2. `.../wf/dml/common/calc_stg.sql`;
3. `.../wf/dml/epk_client/epk_client.sql`.

`epk_client.sql` достигается в четыре перехода. Значение `$datamart_dir` остаётся неизвестным и не угадывается; точное repository-local сопоставление выполняется по оставшемуся пути после подстановки `main_table_name=epk_client`.

## Граница контракта

- изменения ограничены KLC workflow-context materialization;
- parser, core evidence, SQL lineage, PDM и data-model relationships не менялись;
- локальные переменные внутри SQL-скриптов, например `prep_src_table`, не интерпретируются как глобальные workflow bindings;
- полное тестирование всей платформы не выполнялось, поскольку затронут только локальный SQL workflow-context контур.
