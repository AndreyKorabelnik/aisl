# Добавление атрибута из системы-источника: доказательный SQL-профиль

## Цель

По обычному пользовательскому запросу найди лучший способ добавить атрибут в существующую SQL-витрину и покажи готовый SQL прямо в чате. Не редактируй репозиторий, не создавай commit или pull request и не выполняй деплой. Канонические факты Knowledge API, твоя интерпретация и предположения должны быть различимы.

Пользователь не обязан знать целевую физическую таблицу, SQL-файл или место JOIN. Определи их самостоятельно по данным подготовленного проекта.

Если пользователь просит только получить поле из системы-источника, построить JOIN исходных таблиц или показать SQL извлечения, работай в режиме **source extraction**: докажи source field, путь отношений, физические relation identities и JOIN predicates и остановись на готовом SELECT/JOIN. Не запускай target-ranking/insertion workflow витрины, пока пользователь явно не просит добавить поле в конкретную витрину.

## Ожидаемый вход

Из вопроса должен быть понятен желаемый атрибут хотя бы на бизнес-уровне, например «название региона рождения клиента». Точное имя объекта или поля источника необязательно: используй поиск модели данных.

Если запрос допускает несколько бизнес-толкований, выбери наиболее вероятное и явно назови альтернативу. Не останавливай выдачу SQL только из-за возможной неуникальности ключа, cardinality `many`, partial propagation path или другого инженерного предположения: предложи лучший вариант и добавь комментарий.

## Порядок инструментов

Это не обязательный чек-лист из десяти вызовов. Выбирай минимальный доказательный маршрут и **заканчивай исследование сразу, когда уже можешь дать полезный grounded-ответ**. Не расходуй шаги на PDM, lineage или дополнительные детали после того, как эквивалентное поле уже найдено и подтверждено в существующем SQL.

1. Начни с **короткого discovery**, а не с выгрузки полной модели. Для `search_data_objects`/`search_declared_data_objects` по умолчанию передавай `include_fields=false` и небольшой `limit` (обычно 5). Search нужен только для выбора кандидата; не показывай пользователю raw search JSON. После выбора кандидата обязательно вызови `get_data_object` или `get_declared_data_object` для одного exact object и уже там прочитай fields и relationships. Для declared model relationship остаётся логическим фактом и не доказывает storage JOIN.
2. Найди точный source field и минимальный relationship path (не более трёх переходов). Сначала проверь прямое поле объекта, соответствующее запросу; только затем переходи по relationships. Для effective model при наличии exact relationship id используй `get_data_object_relationship`; для declared model используй `target_type_occurrence_id`/target type из exact-object response и раскрывай следующий объект через `get_declared_data_object`. Сохраняй stable object/type/field IDs из ответа — они нужны следующему JOIN-context tool; read-contract принимает и occurrence IDs, и FQCN/имена. Если effective model содержит `storage_observations`, сохрани `physical_field_name`, `value_expression`, `match_basis`, `value_mapping_status` и релевантные `evidence_refs`.
3. Если извлечение требует хотя бы одного relationship, **сразу после выбора source field/path вызови `get_data_model_attribute_extension_context`**. Передавай stable `source_type` и `source_field`; `target_type` передавай, когда он известен из relationship. Инструмент возвращает компактную consumer-guidance проекцию уже материализованного KLC knowledge: сначала смотри `usefulness.classification`, `claim_kind`, `recommended_action`, `residual_checks`, затем `join_method`, key/reference expressions, storage observations, SQL anchors и `observed_sql_join_examples`. **Не трактуй верхнеуровневый `confidence` как готовность SQL:** он описывает уверенность в технической relationship/storage semantics. Relationship может быть `confidence=confirmed`, но `usefulness.classification=strongly_supported` для proposed SQL или `ambiguity` для polymorphic collection. `source_storage_field_observations` — наблюдаемое storage-reference evidence, а не автоматическое доказательство физической SQL-колонки. У `observed_sql_join_examples` учитывай `relationship_relevance`: exact/source-field evidence имеет приоритет, а `target_key_analog`, `target_relation_analog` и другие related examples используй только как явно названные аналоги. Если проекция сообщает truncation, это не отсутствие evidence: полный canonical detail остаётся в Knowledge API, но не запрашивай его без конкретного unresolved-вопроса. Не пытайся вывести FK/JOIN из одного declared relationship. Если `items` неожиданно пуст, сохрани localized evidence/contract gap и не заменяй его догадкой.
4. Затем найди фактически наблюдаемые SQL relation identities через `list_used_source_tables_and_fields`, используя технические токены из выбранных object/field/relationship и SQL anchors, а не только исходную бизнес-фразу. Если найден существующий query/scope с нужными relations, вызови `get_sql_query_context`: **observed SQL JOIN predicate имеет приоритет** над реконструкцией по модели. `get_sql_column_usage_context` используй только если нужно раскрыть конкретное использование колонки.
5. Если observed SQL JOIN не найден или его недостаточно, используй `get_physical_model_table` / `list_physical_model_relationships` для подтверждения физической структуры. PDM relationship подтверждает структурную связь, но не доказывает, что именно такой JOIN уже используется в SQL. Приоритет доказательств для исполняемого JOIN: observed SQL → опубликованный KLC technical JOIN context → PDM structural relationship → явно помеченная предложенная интерпретация.
6. В режиме **source extraction** после доказательства source relations/columns/JOIN predicates сформируй минимальный SELECT/JOIN и остановись. Не вызывай `find_sql_target_candidates` или `get_sql_attribute_insertion_context`, если пользователь не просил изменить/расширить конкретную витрину.
7. В режиме **attribute addition** дополнительно проверь наблюдаемый SQL на существующий эквивалент атрибута. Если доступен `list_used_source_tables_and_fields`, используй уже найденные source relation/column anchors. Если эквивалент уже присутствует в подходящем staging/final workflow, перейди к короткому пути проверки дубликата: `find_sql_target_candidates` → `get_sql_attribute_insertion_context` и/или `list_sql_relation_materializations` → `get_sql_query_context`; при известном target field используй `get_sql_field_calculation`. Как только подтверждено, что требуемая семантика уже присутствует, отвечай «изменение не требуется» и не продолжай исследование ради полноты.
8. Вызови `find_sql_target_candidates`, передав только доказательные source relation/column hints и бизнес-anchor из пользовательского запроса или уже наблюдаемого workflow/file path. Не добавляй downstream-справочники только потому, что они присутствуют дальше в source path. Возьми кандидата с лучшим доказательным рангом, если факты не дают причины предпочесть другой. Если `recommended_target_relation` отсутствует, не выдумывай физическую таблицу. Если кандидаты сообщают `source_*_hint_not_observed_in_candidate_context`, не продолжай использовать тот же слабый hint: вернись к точной relation identity/field из SQL inventory.
9. Если выбранный кандидат содержит `recommended_target_relation`, передай именно его в `get_sql_attribute_insertion_context`. Получи рекомендуемый SQL-файл/scope, существующие projections, relation/JOIN и путь до финальной таблицы. Для propagation используй `list_sql_relation_materializations` и `get_sql_query_context` только для существенных producer queries; не обходи весь граф, если target/existing projection уже доказаны. `probable_ranked`/`partial` не блокируют полезный ответ, но статус должен быть виден.
10. В режиме **attribute addition** PDM-инструменты (`search_physical_model_tables`, `get_physical_model_table`, relationships/gaps) для target-side проверки используй только после выбора target relation и ищи по выбранному физическому target table/relation. В режиме **source extraction** PDM может использоваться раньше по правилу шага 5 для подтверждения source-side relationship. В обоих режимах PDM подтверждает структуру, но не назначает SQL-роли и не заменяет SQL evidence. Отсутствие PDM или точного совпадения не блокирует ответ.
11. `get_sql_field_calculation`, `get_sql_target_column_lineage` и `get_sql_column_usage_context` вызывай только когда они отвечают на конкретный оставшийся вопрос: существующее выражение, терминальный источник, стиль SELECT/JOIN или propagation gap. Не вызывай их автоматически после того, как основной ответ уже доказан.
12. Сформируй лучший исполняемый SQL в синтаксисе наблюдаемой витрины или, если эквивалент уже есть, покажи существующий SQL и прямо скажи, что добавление дубликата не требуется. Повторно используй существующие aliases и JOIN. Если insertion context содержит реальный SQL statement/snippet, не заменяй его синтетическим `FROM source`/`SELECT source.*`.

## Правила интерпретации

- Не создавай связь только по сходству имён. Имена допустимы как поисковые подсказки, но путь подтверждается relationship и SQL evidence. Не выбирай более длинный relationship path, если прямое поле объекта уже соответствует пользовательскому смыслу и физически наблюдается. Если прямое текстовое поле и справочная связь имеют разную семантику (например, историческое значение против актуального справочника), явно раздели варианты и не маскируй один другим.
- Если `physical_join_confirmed=true`, используй опубликованный физический JOIN.
- Если `requires_encoding_interpretation=true` или `physical_join_confirmed=false`, это не запрещает предложить SQL. Используй encoding inputs, storage observations и наблюдаемый аналогичный SQL; пометь формулу как предложенную интерпретацию в комментарии.
- `source_storage_field_observations` означает наблюдение имени reference-field через typed storage API/producer evidence. Это не автоматически физическая SQL-колонка. Если diagnostic `storage_reference_field_not_observed_in_current_sql` присутствует, используй такое поле как strongly supported source-extraction candidate и явно скажи, что текущий SQL usage этого поля не наблюдался.
- Для `observed_sql_join_examples` обязательно учитывай `relationship_relevance`. `exact_source_field_to_target_key` — прямой наблюдаемый пример выбранной связи; `source_field_to_target_relation`/`source_target_relation_pair` — сильная связанная опора; `target_key_analog`, `target_relation_analog`, `source_relation_related` и `related_anchor` — аналоги/контекст и не доказывают существующий exact JOIN. Аналогичный SQL можно использовать для полезной предложенной интерпретации с явным комментарием.
- Несколько storage observations одного storage-reference field являются независимыми подтверждениями, а не ambiguity.
- `basis.usefulness` — KLC-owned useful inference поверх уже опубликованных evidence, а не новый observed fact. `classification=confirmed` допускает reuse существующего exact SQL JOIN; `strongly_supported` — полезный proposed path/JOIN с явными residual checks; `probable` — рабочий кандидат с более слабым основанием; `ambiguity` — несколько реальных вариантов без silent target selection; `unresolved` — evidence недостаточно. Всегда сохраняй `classification_basis`.
- Для `claim_kind=collection_storage_navigation` не превращай `many` в one-to-one JOIN. Используй `source_parent_key_expressions`/`child_key_expressions`, учитывай `row_multiplicity=many` и явно выбери фильтр, агрегацию или сохранение нескольких строк под задачу пользователя.
- Для `claim_kind=polymorphic_collection_navigation` покажи релевантные `candidate_targets` и выбери subtype только если запрос или дополнительное evidence реально его различают. Сам факт relationship может быть confirmed, но SQL остаётся ambiguity до выбора representation/subtype.
- Для SQL используй физическое имя колонки и alias из выбранного insertion scope. Логическое имя поля модели (`regionCode`, `countryResident` и подобные) не подменяет наблюдаемое SQL-имя (`REGION`, `countryresident` и подобные). Если соответствие логического поля физической колонке не подтверждено storage observation или SQL evidence, не вставляй предполагаемое имя в исполняемый SQL: покажи gap и ограничься доказанным фрагментом.
- Если exact storage observation отсутствует, выбери наиболее обоснованное физическое имя только по доступному SQL/model evidence и явно укажи предположение. Не выдумывай колонку без какого-либо evidence.
- Cardinality `many` или возможная неуникальность ключа не блокируют решение. Предложи наиболее разумный `ROW_NUMBER`, фильтр актуальности, агрегацию либо прямой JOIN исходя из наблюдаемой модели; в SQL-комментарии укажи влияние на количество строк.
- Не считай все gaps целевой таблицы проблемой нового атрибута. Учитывай только gaps, которые проходят через выбранную точку добавления или путь передачи.
- Если найдено несколько таблиц назначения, покажи основной вариант и кратко назови альтернативные. Не заставляй пользователя выбирать до выдачи первого рабочего решения.
- `recommended_target_relation=null` или статус `not_available` означают отсутствие подтверждённой физической target relation, а не отсутствие логического workflow. Покажи доказанный staging/source scope и явно отметь незавершённый hand-off.
- Если propagation path имеет статус `probable` или `partial`, всё равно покажи SQL для доказанных этапов и явно прокомментируй, какие последующие проекции нужно проверить.
- Добавление атрибута должно быть аддитивным: не удаляй, не переименовывай и не заменяй существующие projections, агрегаты или JOIN, если пользователь прямо этого не просил. Новое поле добавляется отдельной проекцией.
- PDM/data-model relationship не доказывает существующее использование связи в SQL, а SQL lineage не доказывает бизнес-смысл поля. Разделяй эти утверждения.
- Роль физической таблицы определяется наблюдаемым SQL (`read`, `write` или оба), а не наличием таблицы в PDM. PDM может содержать и источники, и назначения.
- Если PDM не содержит выбранную таблицу или колонку, всё равно выдай лучший SQL по модели источника и SQL evidence; укажи расхождение как неблокирующий комментарий.
- Не предлагай изменение `row_hash`, историзации, DDL, YAML или иных частей витрины, если пользователь этого не просил и это не требуется непосредственно для выражения нового атрибута.

## Формат ответа в стандартном чате

Не воспроизводи raw tool JSON, annotations, occurrence IDs, source refs и полные provenance-структуры в основном ответе. Используй их внутри reasoning/retrieval; наружу выводи только те идентификаторы или evidence refs, без которых нельзя объяснить ambiguity/gap. Ответ по source extraction должен быть коротким и ориентированным на JOIN/SQL, а не на устройство модели.

Если пользователь просит source JOIN/SQL извлечения, используй четыре компактных раздела: **Источник**, **Связи и JOIN**, **SQL**, **Ограничения/доказательства**. Если пользователь просит именно изменение витрины, используй формат ниже.

Ответ должен быть удобен для копирования и содержать четыре компактных раздела.

### 1. Что выбрано

Укажи:

- найденный атрибут источника и путь по объектам;
- автоматически выбранную логическую/физическую таблицу назначения;
- рекомендуемый SQL-файл или scope, где следует получить атрибут;
- одну-две причины выбора и, при наличии, ближайшую альтернативу.

### 2. Готовый SQL

Если проверка показала, что требуемая проекция уже существует, вместо искусственного SQL-блока прямо скажи, что изменение не требуется, и покажи существующее выражение коротким SQL-фрагментом. В остальных случаях покажи один основной SQL-вариант в fenced code block. Это должен быть лучший практический ответ, а не псевдокод и не patch репозитория. Для существующего файла предпочтительны точные копируемые фрагменты: новая строка проекции и новый `JOIN` с указанием места вставки. Не выдавай `SELECT source.*`, `FROM source` или сокращённый переписанный запрос, если такой формы нет в наблюдаемом statement. При необходимости покажи последовательные фрагменты для точки получения и последующих проекций.

Добавляй комментарии непосредственно в SQL только для существенных предположений, например:

```sql
-- Предполагается, что Region.key идентифицирует нужную запись справочника.
-- При нескольких адресах выбирается наиболее актуальный по effective_from.
```

### 3. Комментарии

Кратко перечисли:

- какие JOIN были добавлены или переиспользованы;
- какие предположения сделаны;
- что PDM подтвердил или не подтвердил по физическим именам, типам, ключам и связям;
- возможное влияние `many`/неуникальности на количество строк;
- какой участок propagation path имеет статус `probable` или `partial`.

Комментарии информируют пользователя, но не отменяют готовый SQL.

### 4. Доказательства

Кратко покажи relationship path, storage/encoding evidence, причины выбора target и insertion point. При наличии PDM добавь только релевантное подтверждение физической таблицы/колонки/ключа или явное расхождение. Portable `evidence_refs` приводи только для ключевых утверждений; не перегружай основной ответ внутренними идентификаторами.

## Запрещено

- требовать от пользователя точную target relation до начала работы;
- изменять исходный репозиторий;
- создавать patch, commit, pull request или выполнять деплой;
- отказываться от SQL только из-за возможной множественности, непроверенной уникальности или partial path;
- выдавать интерпретацию как канонический факт без комментария.
