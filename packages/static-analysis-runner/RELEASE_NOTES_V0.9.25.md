# static-analysis-runner 0.9.25

## Iteration 60 — SQL repository routing and artifact validation

### Added

- deterministic repository analyzer routing from profile semantics;
- `code-analyzer-core analyze-sql` invocation for SQL repository profiles;
- SQL-specific minimum core version `0.42.2`;
- streaming validation of the canonical `sql-analysis/v1` artifact;
- validation of the exact 17-shard fact contract, JSONL records, IDs, paths,
  counts, byte sizes, SHA-256 digests, coverage and content fingerprint;
- SQL validation status, coverage status, warning/error codes and fact count in
  repository run manifests and summaries.

### Behaviour

- `analysis_status=partial` is accepted as a completed repository run with the
  warning `analysis_partial`;
- malformed or structurally inconsistent SQL artifacts fail the run;
- generic repository profiles remain on `analyze-java` unless strong SQL profile
  evidence is present;
- SQL runs reject `--foundation-input`;
- SQL Knowledge Layer materialization is explicitly rejected until
  `knowledge-layer-core` supports `sql-analysis/v1`.

### Compatibility

- Java repository, suite and workspace flows are unchanged;
- `knowledge-layer-core>=0.49.1,<1.0.0` remains the supported Knowledge Layer range;
- no compatibility adapter or dual-write SQL contract was added.
