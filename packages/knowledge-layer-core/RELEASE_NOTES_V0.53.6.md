# knowledge-layer-core 0.53.6

## Portfolio topology scale

- Replaced one-DuckDB-import-per-repository topology ingestion with batched inserts.
- `analysis_suite`, `analysis_task`, `analysis_artifact` and `analysis_task_artifact` are inserted once per portfolio build.
- `analysis_record` is inserted in bounded 25,000-row batches.
- Matching, island semantics and exported contracts are unchanged.

## Scale validation

An AT900-like synthetic portfolio with 1,600 repositories, 35 inbound and 6 outbound HTTP boundaries per repository (65,600 interface records total), was built with one DuckDB thread and a 512 MB DuckDB limit in 27.546 seconds. The pre-change implementation did not complete the same workload within 600 seconds.
