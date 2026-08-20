# Test status — knowledge-api 0.19.1

- full Knowledge API test suite: **60 passed**;
- compileall: PASS;
- OpenAPI document regenerated and contract equality test: PASS;
- real HTTP publication/query against KLC 0.59.26 `sql-target-source-mapping/v1` + real PDM: PASS (HTTP 200);
- real response: **93 target entries = 86 mapped + 7 gap-only**, 294 diagnostics;
- `epk_id`: 2 sources; `client_centaur_flag`: 2 sources;
- PDM display spelling gate: `confirmedByOperator`, `riskProfile`, `investingHorizon`, `pon_managerCode`: PASS;
- unresolved placeholders remain verbatim and mappings remain partial: PASS.
