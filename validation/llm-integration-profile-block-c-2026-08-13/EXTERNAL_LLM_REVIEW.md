# External LLM Review — Consumer Kit acceptance

Date: 2026-08-13
Reviewer role: external LLM consumer. The review deliberately uses only the generated Consumer Kit contract; it does not rely on the Knowledge Assistant agent loop.

## UCP + SQL + PDM kit

Scope:
- system_id: `ucp-sql-pdm`
- revision_id: `rev-real-ucp-sql-pdm`
- capabilities: 44
- exported HTTP tools: 16
- profile: `attribute-addition-plan/v1`

The tool set contains declared-model search/read, physical-model table/relationship access, SQL source inventory, target candidate/insertion context, query/materialization context, calculation/column usage/lineage, and cross-artifact attribute-extension context. The retrieval guide explicitly separates declared-model relationships from physical JOIN/storage semantics and requires visible gaps/ambiguity instead of guessing.

## Question 1: «дай связи таблиц для получения поля гражданство»

A grounded external consumer can follow this minimal route:
1. `search_declared_data_objects` to locate citizenship/country-related model objects or fields by name/documentation.
2. `get_declared_data_object` to inspect declared relationships while preserving the warning that a declared relationship is not a physical JOIN.
3. If a target/relation is known, use `search_physical_model_tables`, `get_physical_model_table`, and `list_physical_model_relationships` for physical table/key/relationship evidence.
4. If the question concerns the actually observed SQL path, use `list_used_source_tables_and_fields` and `get_sql_target_column_lineage` rather than inferring a JOIN from names.
5. If model-to-storage encoding is the missing bridge, use `get_data_model_attribute_extension_context` and preserve its confidence/gaps.

Conclusion: the kit contains the capabilities, HTTP-bound tools and evidence discipline needed to answer the question without private Knowledge Assistant logic.

## Question 2: «дай SQL для добавления поля гражданство в витрину»

A grounded external consumer can follow the exported retrieval guide:
1. Find the source object/field through the declared-model tools.
2. Check existing SQL with `list_used_source_tables_and_fields` before proposing a duplicate field.
3. Use `find_sql_target_candidates` to locate evidence-backed target candidates.
4. Use `get_sql_attribute_insertion_context` for the observed insertion scope, projections and JOIN context.
5. Use `list_sql_relation_materializations` / `get_sql_query_context` only for the material propagation steps still needed.
6. Use PDM tools only after the SQL target is selected, as structural confirmation rather than target-role inference.
7. Use field-calculation/lineage tools only for unresolved calculation/source questions.

Conclusion: the kit is structurally sufficient for an external LLM to construct a grounded SQL proposal while distinguishing observed SQL from proposed interpretation. This acceptance does not grade the quality of any particular generated SQL.

## Question 3: «откуда рассчитывается поле X»

Minimal route:
1. `get_sql_field_calculation` for the observed expression/calculation context.
2. `get_sql_target_column_lineage` for upstream/terminal origins and propagation status.
3. `get_sql_column_usage_context` only if additional SELECT/JOIN usage context is required.

Conclusion: the required lineage/calculation tools are exported for the UCP+SQL+PDM revision.

## Narrow revision negative control

Scope:
- system_id: `narrow-interactions`
- revision_id: `rev-narrow-interactions`
- capabilities: 5
- exported tools: 16 interaction/system-description tools

No SQL, PDM, physical-model or SQL-lineage tools are exported. This demonstrates capability-driven gating rather than application/scenario-name gating.

## Live direct HTTP proof

A separate typed fixture was published through Knowledge API. A Consumer Kit was generated without `knowledge-assistant` on `PYTHONPATH`. Then a fresh stdlib-only Python process — with no framework packages at all — read `llm_integration_profile.json`, selected `search_declared_data_objects`, constructed the HTTP request from its `api_binding`, injected the pinned revision, and called Knowledge API directly.

The response contained observed evidence for:
- `com.acme.Individual.birthCountry`
- documentation: `Страна рождения`
- declared relationship count: 1

Result: `EXTERNAL_HTTP_TOOL_CALL_PASS`.

## Review conclusion

The external-consumer boundary is structurally proven for Block C. Knowledge Assistant is not required to understand the available revision capabilities, choose an exported tool, derive its HTTP operation or maintain revision pinning. Prompt/answer quality remains intentionally outside this acceptance block.
