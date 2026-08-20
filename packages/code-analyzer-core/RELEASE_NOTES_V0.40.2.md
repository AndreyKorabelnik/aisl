# code-analyzer-core 0.40.2

Iteration 28.2A fixes duplicate persistence evidence in profiles that run both `java_persistence_lineage_build` and `java_data_model_lineage_build`.

- the pipeline remains the single owner of already-emitted persistence facts;
- the data-model builder can reuse persistence facts without republishing them;
- direct standalone calls preserve the previous self-contained behavior by default;
- regression coverage verifies reuse without duplicate `storage_lineage_gap` facts.
