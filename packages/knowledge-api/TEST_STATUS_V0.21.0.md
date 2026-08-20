# Test status — knowledge-api 0.21.0

- Targeted SQL/data-model/OpenAPI contract tests: 26 passed.
- Full pytest suite: 63 passed.
- `python -m compileall -q knowledge_api`: passed.
- Public OpenAPI regenerated and contract test passed.
- Real HTTP smoke against existing revision `rev-e7cdcc1a0c26bb20499a258f`: HTTP 200, `sql-target-column-lineage/v1`, one lineage path for `custom_b2c_profile_fl.epk_client.birth_dt`, zero gaps.
- Real Knowledge Assistant tool smoke on the same revision: `get_sql_target_column_lineage` completed successfully.
- The real smoke reused the already published prepared revision; no Core, Runner or KLC production rerun occurred.
