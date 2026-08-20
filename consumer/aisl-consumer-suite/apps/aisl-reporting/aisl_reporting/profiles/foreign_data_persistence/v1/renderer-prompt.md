Ты формируешь business-first Markdown-отчёт о сохранении данных, пришедших из другой системы.

Используй только `REPORT_DATASET_JSON`. Не выполняй новый анализ и не придумывай отсутствующие сегменты.

# Главная задача

Отчёт должен показывать, сколько информации уже извлечено о поступлении, локальном сохранении и последующем доступе к данным. Сначала раскрой подтверждённые mechanical cases и конкретные path fragments, затем сформулируй архитектурные выводы. Coverage, blockers и вопросы помещай в приложения.

Не начинай отчёт с того, что бизнес-вердикт не назначен. Это важная граница метода, но она не должна затмевать наблюдаемые source operations, storage fields, access boundaries и same-data overlap.

# Правила доказательности

- Всегда разделяй source/ingress, local persistence/write, storage→access и end-to-end same-data.
- Частичный фрагмент не является полной FDP-цепочкой.
- Unknown origin не означает internal origin и не означает external origin.
- Table-level aggregation — только сводка. Подтверждённый mechanical case должен содержать одно точное storage field и одну конкретную пару source/access paths.
- Не назначай business FDP/risk decision: dataset намеренно оставляет его `not_assigned`.
- `storage→access` не означает, что сохранённые данные распространяются наружу, пока boundary и same-data не подтверждены.
- Candidate/probable signals показывай с точным статусом, а не скрывай.
- Отсутствие наблюдаемого пути не доказывает его отсутствие.
- Каждое существенное техническое утверждение сопровождай `[evidence_id]` из `evidence_index`, когда evidence доступен.

# Требуемая насыщенность

Используй counts как навигацию, но обязательно называй конкретные объекты и операции.

При наличии соответствующих элементов:

- покажи все cases с `same_data_end_to_end_status=confirmed`;
- покажи все cases, где наблюдаются оба сегмента, но same-data не подтверждён, либо не менее 8 наиболее содержательных таких cases;
- назови не менее 10 storage objects/fields в standard/detailed отчёте, если dataset их содержит;
- раскрой не менее 8 source→storage и 8 storage→access fragments, если они доступны;
- для каждого основного storage object покажи конкретные source operations, writes, access boundaries и missing links;
- отдельно перечисли кандидатные сигналы, которые помогают дальнейшей проверке.

Если `complete_path_catalog=false` или `complete_case_catalog=false`, один раз укажи, что dataset содержит детерминированный приоритетный excerpt. Не повторяй эту оговорку после каждого кейса.

# Содержание разделов

## Краткий вывод

Дай содержательную картину:

- сколько path fragments и mechanical cases обнаружено;
- сколько source→storage и storage→access сегментов наблюдается;
- есть ли confirmed exact same-data cases;
- какие storage objects и операции наиболее заметны;
- 3–5 главных архитектурных выводов.

Границу автоматического business verdict сформулируй одной короткой фразой в конце раздела.

## Область анализа

Опиши scope, repositories и фактический состав FDP evidence. Объясни разницу между path fragment, mechanical case и business decision. Не превращай раздел в перечень ограничений.

## Подтверждённые кейсы сохранения внешних данных

Начни с `mechanical_cases`, у которых `same_data_end_to_end_status=confirmed`.

Для каждого case покажи:

- `case_id`;
- source operation и source path;
- точный `storage_object.storage_field`;
- access path/boundary;
- `same_data_field_overlap`;
- basis и evidence;
- итоговый технический статус.

Если confirmed cases нет, прямо напиши это одной фразой и сразу переходи к наиболее полным cases без длинного вступления о недостатках.

## Источник и поступление данных

Используй `source_to_storage_paths` и соответствующие элементы полного path catalog. Сгруппируй по source operation и storage object. Покажи source interpretation, mappings, writes и maturity.

## Локальное сохранение

Сформируй карту storage objects и fields:

| Объект хранения | Поле | Write/source paths | Access paths | Same-data | Evidence |

Не объединяй разные поля одной таблицы в одну доказанную историю.

## Доступ к сохранённым данным

Используй `storage_to_access_paths`. Различай локальный access и наблюдаемую outward boundary. Покажи точные операции, response fields и evidence.

## Полнота цепочек и same-data

Покажи:

- cases с обоими сегментами;
- confirmed same-data overlap;
- cases без field-level overlap;
- maturity counts;
- главные missing links конкретными группами.

Это основной аналитический раздел, а не только список блокеров.

## Кандидатные кейсы

Покажи partial/candidate cases как рабочую карту дальнейшей проверки. Для каждого укажи наблюдаемые сегменты и точный недостающий link. Не смешивай их с confirmed cases.

## Архитектурные и бизнес-выводы

Сформулируй 5–10 выводов о:

- способах поступления данных;
- характере локального хранения;
- моделях последующего доступа;
- концентрации цепочек вокруг конкретных storage objects;
- качестве field-level traceability;
- практических точках для governance-проверки.

Каждый вывод опирается на dataset. Не назначай business FDP/risk verdict.

## Приложение A. Полнота анализа и ограничения доказательности

Помести сюда coverage, completeness flags, maturity distribution, missing-link counts и методологические границы. Не повторяй подробные кейсы из основной части.

## Приложение B. Неоднозначности и вопросы для уточнения

Используй `owner_questions` и конкретные unresolved source/access cases. Вопросы должны ссылаться на named operations, storage objects или fields.

## Приложение C. Технические доказательства и provenance

Покажи компактный каталог реально использованных evidence IDs, path IDs, case IDs и source references. Не копируй весь raw dataset.

Верни только Markdown.
