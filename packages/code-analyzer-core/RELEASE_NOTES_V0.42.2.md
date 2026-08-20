# Release notes — code-analyzer-core 0.42.2

Iteration 59 publishes the first canonical streaming artifact for SQL analysis.

## Changes

- Added the versioned `sql-analysis/v1` artifact under `sql-analysis/`.
- Added 17 deterministic JSONL fact shards:
  - `sql_statement`;
  - SQL script statements, bindings, embedded SQL, and invocations;
  - semantic placeholders;
  - SELECT scopes;
  - relations and column usages;
  - projections;
  - write targets and target/projection bindings;
  - JOIN edges;
  - direct and recursive field lineage;
  - object dependencies;
  - localized lineage gaps.
- Added `sql-analysis/manifest.json` with:
  - contract and schema versions;
  - repository and producer identity;
  - shard paths, counts, ID fields, byte sizes, and SHA-256 values;
  - coverage reference;
  - deterministic content fingerprint;
  - serialization and compaction policy.
- Added `sql-analysis/coverage.json` with resolution distributions for relations, fields, projections, writes, JOINs, lineage, placeholders, script invocations, and gaps.
- Added canonical `sql_object_dependency` facts derived from write-from-read table lineage.
- Canonical facts contain repository-relative evidence only. Machine-local paths are removed.
- Repeated generic maturity policy blocks are omitted from the ingestion artifact while typed resolution statuses, evidence, expressions, and identities are retained.
- Legacy aggregate lineage, mart lineage, source-table summaries, navigation samples, and full query payloads are excluded from the canonical artifact.
- Added public streaming validator `validate_sql_analysis_artifact`.
- Validator checks:
  - artifact/schema contract;
  - exact fact shard contract;
  - safe relative paths;
  - JSONL structure;
  - required and unique fact IDs;
  - record counts, sizes, and SHA-256;
  - repository-relative evidence policy;
  - coverage hash and schema;
  - content fingerprint.
- Partial analysis coverage is returned as a warning, not a structural validation failure.
- Top-level analysis manifest, diagnostics, and `run_sql_analysis` result now expose the canonical artifact path, status, schema version, and content fingerprint.
- SQL profile version advanced from `1.2` to `1.3`.
- Package and runtime versions are synchronized at `0.42.2`.

## Compatibility

`sql-analysis/v1` is the only canonical SQL ingestion artifact for future runner/KLC integration. Existing large JSON outputs remain diagnostic core outputs and are explicitly excluded from the canonical manifest; no compatibility JSON shards are written inside `sql-analysis/`.
