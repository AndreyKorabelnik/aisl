# code-analyzer-core 0.40.3

Iteration 28.2B makes constructor lineage type-safe and scope-aware.

- resolves constructor targets by exact FQCN, declaring package, explicit imports, wildcard imports, or a unique simple name;
- never overwrites one observed Java type with another merely because their simple names match;
- publishes one `constructor_target_type_ambiguous` diagnostic when source context cannot select between observed declarations;
- suppresses unresolved constructor-argument gaps from test and generated source while retaining confirmed mappings;
- records constructor resolution and suppression counters in data-model lineage status;
- preserves constructor resolution metadata in compact `data_model_lineage_gaps.json`.

The implementation is repository-neutral and contains no AT900/UCP/package/class/field-specific rule.
