# code-analyzer-core 0.44.0

## Generic storage and SQL evidence

- Registered `storage-usage-evidence/v1` through `java-storage-usage-analyzer`.
- Registered existing canonical `sql-analysis/v1` through `sql-analysis-analyzer`.
- Both analyzers execute only through `core_evidence_runtime/v1` and return `core_evidence_artifact_contract/v1` envelopes.
- Reused existing Java call observations and SQL parsing; no duplicate parser or inferred physical names were added.
- Removed the public legacy `analyze-sql` CLI route. The SQL implementation remains an internal analyzer dependency.
- Runner specialization is not required for either evidence family.
