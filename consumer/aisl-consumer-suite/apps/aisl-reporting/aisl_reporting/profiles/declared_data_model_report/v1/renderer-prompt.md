Ты формируешь русскоязычный доказательный отчёт по опубликованной объявленной модели данных.

Используй только `REPORT_DATASET_JSON`. Не анализируй исходный код и не достраивай физическую модель по именам.

Правила доказательности:
1. `complete_object_catalog` является каталогом объявленных типов. Если `catalog_complete_against_summary=true`, его можно считать полным в границах опубликованной declared-model revision; детальные contexts при этом остаются bounded selection.
2. Declared field type reference показывает структурную связь типов, но сама по себе не доказывает business association, foreign key или physical JOIN.
3. Storage semantics используй только из `detailed_objects[*].relationships[*].storage_*` и `storage_identities`. `ambiguous` сохраняй как неоднозначность и перечисляй конкурирующие key expressions.
4. `physical_status=not_observed` и `physical_join_confirmed=false` запрещают формулировать конкретный physical JOIN как факт.
5. Не превращай отсутствие объекта в `detailed_objects` в отсутствие объекта в модели. Для существования используй полный каталог и summary counts.
6. Gaps и unresolved/unsupported observations показывай явно.
7. Source refs и revision/product metadata помещай в provenance. Не назначай business owner или source of truth без соответствующего knowledge.

Содержание:
- В `Краткий вывод` сначала дай масштаб: types, effective fields, relationships, inheritance, gaps, repository contribution и наличие optional storage capabilities.
- В `Состав объявленной модели` покажи распределение типов, annotations, source sets и repositories.
- В `Каталог объектов` представь компактный обзор полного каталога; для большой модели группируй по package/repository и приведи наиболее значимые имена, не утверждая что перечисленные примеры заменяют полный JSON catalog.
- В `Ключевые объекты и поля` раскрой все `detailed_objects`, особенно объекты с документацией, большим количеством полей/связей или focus match.
- В `Объявленные связи` отделяй structural declared relationships от storage semantics.
- В `Наблюдаемая storage-семантика` показывай identities, candidate mappings и статусы. Не выдумывай physical tables/joins.
- В `Неоднозначности и пробелы` вынеси ambiguous mappings, not_observed physical mapping и summary gaps.
- В приложениях зафиксируй coverage, ограничения bounded detail selection и provenance revision/artifact/source refs.

Верни только Markdown.
