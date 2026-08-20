# Test results — knowledge-layer-core 0.53.6

- `compileall knowledge_layer_core`: passed.
- Focused topology, interaction graph and offline validation: 24 passed.
- AT900-like 1,600 repository benchmark: passed.
- Benchmark workload: 65,600 HTTP interface records, 1,600 interactions, 9,600 diagnostics.
- Build time: 27.546 seconds with one DuckDB thread and `512MB` DuckDB memory limit.
- Peak process RSS: approximately 1.1 GB.
- Pre-change 0.53.5 comparison: identical 1,600 repository benchmark did not complete within 600 seconds.
