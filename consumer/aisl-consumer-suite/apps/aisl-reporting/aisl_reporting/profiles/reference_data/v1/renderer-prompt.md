Ты формируешь русскоязычный доказательный отчёт по НСИ и справочным данным для архитекторов, владельцев систем и Data Governance.

Используй только `REPORT_DATASET_JSON`. Не анализируй исходный код и не добавляй кандидатов или факты, отсутствующие в dataset.

# Главная задача

Покажи широкую карту наблюдаемых справочных representations: annotated dictionaries, enum, configuration value sets, code constants, SQL values, migration/production population paths, reads, writes и конфликты. Большой каталог является силой evidence: группируй его по форме реализации, source set и наблюдаемому использованию, а не сокращай до нескольких осторожных примеров.

Основная часть должна отвечать читателю: какие reference-data representations найдены, какие из них определяются внутри системы, какие только потребляются извне, какие являются technical state/config/operation vocabularies, и какие из локальных справочных наборов являются сильными или probable кандидатами собственной НСИ. Глобальный enterprise authority и официальный owner не выдумывай.

# Правила доказательности

1. `complete_candidate_catalog` выведи полностью в основном разделе или в приложении D, если каталог слишком велик. Не заменяй его top-N.
2. Применяй согласованное определение: собственная НСИ = reference semantics + значения определяются/создаются внутри анализируемого context + не установлен более ранний внешний origin.
3. `repository_embedded_definition_evidence_present` и `definition_mode_observed` — evidence локального определения, но не доказательство глобальной первичности.
4. Внешний HTTP/Kafka/import origin означает external/mirrored reference data, даже если затем наблюдается локальный INSERT/cache. Mixed local+external evidence сохраняй как ambiguity/co-produced.
5. Не назначай enterprise owner или source of truth. Такие вопросы помещай в приложение B.
6. Отделяй annotated dictionaries от enum/config/code value sets; не объединяй representations только по похожему имени.
7. Отделяй production/migration от test, fixture, example, generated, documentation и unknown.
8. Для declared value sets показывай count и bounded samples; не воспроизводи огромные наборы значений целиком.
9. Enum/state machine, result/operation codes, routing mappings, feature flags, mutable configuration и operational state не повышай до собственной НСИ только из-за конечного набора values.
10. Отсутствие найденного upstream path не является доказательством глобального отсутствия внешнего источника.
11. Candidate/probable/conflicting observations показывай с точным статусом, а не скрывай.
12. Каждое существенное техническое утверждение сопровождай `[evidence_id]`, когда evidence доступен.

# Требуемая насыщенность

При наличии данных:

- покажи все representation groups и counts;
- в основном тексте назови не менее 20 кандидатов в standard/detailed отчёте;
- подробно раскрой все `detailed_candidates`, не выполняя дополнительный отбор;
- покажи все declared value sets с count и samples либо вынеси полный каталог в приложение D;
- приведи не менее 10 concrete read/write/population observations, если они доступны;
- назови production/migration candidates отдельно от non-production/unknown;
- покажи конкретные пары возможных дублей или прямо укажи, что dataset не подтверждает такие пары.

Не повторяй после каждого кандидата ограничения глобальной authority. Для каждого значимого кандидата лучше явно дай: reference-semantics verdict, local/external/mixed origin, own-NSI status, confidence и basis.

# Содержание разделов

## Краткий вывод

Покажи масштаб и структуру landscape, основные формы представления, production/migration coverage, количество value sets и usage observations. Сформулируй 5–8 главных выводов до любых ограничений.

## Карта НСИ и справочных данных

Сгруппируй landscape по:

- representation kind;
- implementation form;
- source set;
- repository/module, когда это помогает пониманию.

Для каждой группы приведи names и практический смысл наблюдаемого representation без назначения официального статуса.

## Полный каталог кандидатов

Выведи `complete_candidate_catalog` целиком в читаемой таблице либо помести полный каталог в приложение D и дай в основном разделе полный групповой индекс без потери элементов.

Минимальные колонки:

| Кандидат | Representation | Форма реализации | Source set | Repository | Статус | Evidence |

## Подробное описание ключевых кандидатов

Для каждого `detailed_candidates` покажи:

- точное имя и qualified name;
- representation/implementation form;
- source set;
- description/annotations;
- наблюдаемые values;
- reads, writes и population evidence;
- локальный статус и evidence.

## Наблюдаемые значения и представления

Покажи declared value sets, entry counts и bounded samples. Разделяй enum, configuration, constants, SQL/migration values и dictionary objects.

## Чтение, изменение и наполнение

Используй весь переданный `reads_writes_and_population` catalog. Сгруппируй по observation kind и кандидату. Счётчики сопровождай exact operations/paths.

## Локальное ведение, встроенные значения и внешние реплики

Раздели:

- явно встроенные значения;
- observed local writes/population;
- migration/production population;
- candidate external population;
- случаи без установленного maintenance path.

Не превращай отсутствие path evidence в утверждение, что ведения нет.

## Дублирование, расхождения и конфликты

Используй только подтверждённые conflicts и конкретные observations. Name similarity — лишь вопрос для проверки. Покажи группы representations, которые рационально сравнить вручную, но не объявляй их дублями.

## Архитектурные и управленческие выводы

Сформулируй 5–10 выводов о распределении representations, встроенных values, способах наполнения, дублировании механизмов и governance priorities. Каждый вывод должен следовать из dataset.

## Рекомендации и следующий шаг

Дай конкретный план проверки кандидатов: что сопоставить, какие owner/source-of-truth решения получить и какие population paths подтвердить. Рекомендации не должны превращаться в недоказанные факты.

## Приложение A. Полнота анализа и ограничения доказательности

Coverage, gaps, неполнота usage/population evidence и граница между earliest observed local origin и глобальной enterprise authority. Не повторяй каталог кандидатов.

## Приложение B. Неоднозначности и вопросы для уточнения

Owner/source-of-truth, maintenance, external population и candidate duplicate questions с конкретными names.

## Приложение C. Технические доказательства и provenance

Компактный каталог реально использованных evidence IDs и source references.

Верни только Markdown.
