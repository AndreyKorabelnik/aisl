# code-analyzer-core 0.43.21

Introduces the official read-only `core_analysis_catalog/v1` contract.

The new `analysis-catalog` CLI command exports Core-owned information about:

- all declared and resolved analysis profiles;
- profile inheritance and source fingerprints;
- the reusable Foundation fragment;
- actual Java runtime stage control versus declarative SQL/spec stage labels;
- current stage categories, observed inputs/outputs and Java derived-stage dependencies;
- profile evidence outputs, capabilities and output contracts;
- architecture diagnostics for hidden shared-state dependencies and knowledge materialization currently performed inside Core.

The catalog has no execution effect. Repository analysis, Foundation creation, profile resolution and output contracts remain unchanged.

This is the first step toward the target boundary where Core publishes independent evidence and Knowledge Layer materializes cross-evidence knowledge.
