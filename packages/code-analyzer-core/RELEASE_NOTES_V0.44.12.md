# code-analyzer-core 0.44.12

## System Description lightweight runtime

`system-description-evidence/v1` now uses a dedicated analyzer-owned pipeline that stops after the evidence needed for system description.

Removed from the System Description runtime path:
- deep `java_persistence_lineage_build`;
- `java_data_model_lineage_build`;
- full declared-value extraction;
- reference-data materialization preparation.

The evidence contract remains `system-description-evidence/v1`. KLC and Reporting contracts are unchanged.
Reference Data keeps its existing pipeline and behavior.
