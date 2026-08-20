# static-analysis-runner 0.9.39 — observed Java derived-stage contracts

## Added

- read-only observed contracts for every Java derived-evidence stage declared by installed Core profiles;
- explicit inputs, upstream stage dependencies, actual `AnalysisResult` reads and mutations;
- produced fact families, direct artifacts, options affecting evidence and fallback behavior;
- current serialization boundary and Suite-local reuse assessment (`ready`, `conditional`, `blocked`);
- source references to both `pipeline.py` bindings and scanner implementations;
- deterministic Markdown export through `mechanism-catalog --stage-contracts-markdown`.

## Key findings on Core 0.43.20

- `java_persistence_lineage_build` is the strongest first candidate for one execution per Suite;
- `java_data_model_lineage_build` is blocked because it can rebuild persistence internally and changes output composition based on pipeline history;
- `java_table_observation_build` accepts all accumulated facts but actually reads only `jpa_entity` and `jpa_relationship` facts plus DB schema;
- safe reuse requires typed persisted fact bundles and fingerprints; the diagnostic table is not a runtime registry.

## Runtime behavior

No Suite, Task, Core Profile, Foundation, stage order, Knowledge Layer or output behavior changed.
