# Test status — knowledge-api 0.19.2

- full Knowledge API test suite: **61 passed**;
- focused endpoint/OpenAPI/API-contract tests: **15 passed**;
- compileall: PASS;
- OpenAPI regenerated; contract equality included in passing suite;
- implementation delegates attribute-extension reads to KLC 0.59.35 `KnowledgeLayerQuery`; API-owned DuckDB query module removed;
- real publication/query against clean Runner 0.10.9 / KLC 0.59.34 product artifact using KLC 0.59.35 read contract: PASS (HTTP 200);
- real C2 `BirthPlace.country -> Country`: exactly 1 result, `resolve_reference_value_to_target_key / confirmed / transformation_required`; exact structural `Country_ + code` correspondence and `Country.name` SQL usage preserved;
- real C5 `Individual.identifications`: polymorphic collection, 8 concrete targets, unresolved SQL status and explicit gap preserved;
- API performs no JOIN classification, key comparison, physical-table resolution or SQL generation.
