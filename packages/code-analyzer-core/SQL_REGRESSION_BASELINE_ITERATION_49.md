# SQL regression baseline — iteration 49

## Real repository

`datamart_profile_fl`, 306 SQL files.

## Baseline before script classification (core 0.41.1)

- published SQL queries: 2,112
- query types dominated by `alias` (1,064), `anonymous` (393), `command` (106), and `unknown_sql` (91)
- mart inventory: 184
- source table usage: 1,396
- mart column lineage: 190
- source join evidence: 224
- SQL mart lineage gaps: 932

## Result after iteration 49 (core 0.41.2)

- top-level SQL queries: 475
- separate script statements: 1,866
- script statements containing nested SQL tokens: 169
- script statements referencing SQL paths: 160
- mart inventory: 182
- source table usage: 1,351
- mart column lineage: 190
- source join evidence: 221
- SQL mart lineage gaps: 348

The two mart inventory records no longer treated as top-level SQL are conditional `CREATE EXTERNAL TABLE` fragments inside the DSL function in `wf/ddl/ddl_custom_b2c_profile_fl.sql`. They remain available as `sql_script_statement` evidence with `contains_embedded_sql=true` and are intentionally deferred to the next bounded script-semantic iteration.

## Selected regression fixtures

1. `wf/ddl/ddl_custom_b2c_profile_fl.sql` — DSL functions, assignments, conditionals, dynamic DDL and MSCK.
2. `wf/ddl/ddl_custom_b2c_profile_fl_t_dim_realestate_and_vehicles.sql` — explicit CREATE/DROP/MSCK DDL.
3. `wf/dml/application_list/application_list.sql` — CTE, `explode`, nested structures.
4. `wf/dml/common/hist_inc.sql` — reusable template SQL with semantic placeholders and multiple CTEs.
5. `wf/dml/common/snp_inc.sql` — CTE chain, wildcard projections and joins.
6. `wf/dml/common/calc_inc.sql` — DSL control flow and `runAndSaveSqlHdfs` invocations.
7. `wf/dml/epk_client/epk_client.sql` — large CTE/UNION business transformation.
8. `wf/dml/epk_client/post_checks.sql` — SQL nested in DSL assignments and control flow.
9. `wf/dml_inc/epk_client/main_epk_client_t0_individual.sql` — nested SELECT in assignment plus top-level DDL/DML.
10. `wf/dml_inc/t_dim_real_estate/t_dim_real_estate.sql` — semantic helper invocations and statistics SELECTs.
11. `wf/dml/epk_persdata_mapping/epk_persdata_mapping.sql` — complex CTE query currently parsed partially.
12. `wf/service/migration.sql` — SQL-file invocations and migration orchestration.
13. `wf/service/drop_partitions.sql` — conditional ALTER/DROP inside DSL control flow.
14. `wf/service/stg_union_crop/script_address.sql` — operational DDL and MSCK statements.
15. `wf/dml/common/tv_stg_table_dedup.sql` — window function, wildcard projection and filter.

## Iteration-49 invariant

Only statements whose top-level token is SQL are passed to the SQL parser. DSL fragments remain queryable as separate evidence and are not silently discarded.
