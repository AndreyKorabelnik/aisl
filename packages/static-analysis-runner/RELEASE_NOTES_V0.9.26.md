# static-analysis-runner 0.9.26

## Iteration 62 — SQL Knowledge Layer materialization

### Added

- one-call SQL workflow:
  `repository -> analyze-sql -> sql-analysis/v1 -> knowledge-layer.duckdb`;
- automatic Knowledge Layer mode selection:
  SQL profiles use `sql`, other repository profiles use `data-model`;
- direct invocation of `knowledge-layer-core build_sql_knowledge_layer`;
- SQL source-fingerprint verification after materialization;
- SQL Knowledge Layer status and producer version in repository run manifests;
- integration coverage against `knowledge-layer-core 0.50.0`.

### SQL artifact boundary

The runner no longer owns a fixed list or fixed count of SQL fact files. It validates
all streams declared by `sql-analysis/v1` manifest:

- safe relative path;
- unique fact type and path;
- declared ID field;
- JSONL structure and unique IDs;
- record count, byte size and SHA-256;
- repository-relative evidence;
- coverage and aggregate content fingerprint.

A concrete Knowledge Layer importer remains responsible for declaring which typed
streams it can materialize. Therefore an additive producer stream does not require a
runner release, while incompatible KLC schemas still fail explicitly during
materialization rather than being silently ignored.

### Compatibility

- requires `code-analyzer-core>=0.42.2` for SQL analysis;
- requires `knowledge-layer-core>=0.50.0,<1.0.0` for Knowledge Layer operations;
- no compatibility adapter, dual write or legacy SQL materialization path was added.
