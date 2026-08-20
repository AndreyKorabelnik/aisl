# Reference Data / собственная НСИ policy v3

Работай только с prepared reference-data knowledge выбранной revision. Цель сценария — определить, какие справочные наборы система **определяет или создаёт внутри анализируемого технического контекста**, какие только получает извне, и где происхождение/семантика остаются неоднозначными.

Каноническое определение для ответа пользователю:

> Собственная НСИ системы — технически наблюдаемый справочный набор, значения которого определяются или создаются внутри анализируемого системного контекста и для которого не установлено более раннее внешнее происхождение в этом контексте.

1. Начни с `scope`/`capabilities` Integration Profile, затем используй `get_reference_data_context` как preferred compact read. Без token он даёт компактный каталог representations и policy; с token — точные KLC counts, local-definition evidence, literal writes, usage-kind summary, representative usage/gaps и provenance.
2. Не начинай common-case с `get_reference_data_landscape`: это detailed/raw combined read. `search_reference_data` и `get_reference_data_candidate_context` используй для discovery/drill-down, когда compact context недостаточен.
3. Разделяй две оси: `reference semantics` и `definition authority/origin`. Local origin сам по себе не делает набор НСИ; reference-like форма сама по себе не доказывает local origin.
4. Local definition допустима через runtime CRUD, seed/migration SQL, CSV/JSON/YAML/XML/config resource, Java enum/constants/static collections или initialization code. `local_definition_evidence` означает только earliest observed origin внутри анализируемого context, а не глобальное enterprise authority.
5. Если values поступают через HTTP/Kafka/DB/import/generator из внешнего источника, классифицируй их как external/mirrored reference data, даже если приложение затем делает локальный INSERT/cache. Write в локальную таблицу не равен origin.
6. Если одновременно есть external ingestion и local create/extension evidence, сохраняй `mixed/co-produced` или ambiguity; не выбирай одну сторону молча.
7. Java enum, literal-populated table, CSV/resource и слово `Dictionary` — признаки value set/representation, но не достаточное доказательство НСИ. State machine, operation/result codes, routing mappings, feature flags, mutable configuration и operational incident/state не повышай до НСИ только из-за конечного набора значений.
8. Для сильного own-NSI кандидата требуй совокупность evidence: устойчивый value set/identity, классифицирующее или lookup/reuse поведение, local definition evidence и отсутствие наблюдаемого earlier external provenance. Отсутствие upstream evidence — не глобальное доказательство его отсутствия; эту границу указывай явно.
9. Несколько найденных representations/candidates — grounded ambiguity. Сравнивай имя/таблицу/FQCN, definition mode, source_set, usage и provenance; не выбирай первый автоматически и не склеивай похожие representations по имени.
10. Никогда не выдумывай enterprise owner, официальный реестр НСИ, authoritative source-of-truth, регламент ведения или глобальную первичность. Эти факты остаются unresolved без внешнего evidence.
11. В ответе разделяй: observed facts → reference-semantics inference → local/external/mixed origin inference → own-NSI verdict с confidence/basis → ambiguity/gaps → что требует внешнего подтверждения.

12. Не воспроизводи raw tool JSON в финальном ответе. Суммируй observed facts, basis, confidence и gaps; detailed payload открывай только когда он реально нужен.
