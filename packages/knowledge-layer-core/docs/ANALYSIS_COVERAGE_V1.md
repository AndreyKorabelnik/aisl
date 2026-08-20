# Analysis coverage contract v1

`analysis_coverage/v1` is a deterministic projection over facts and limitations already materialized in the Knowledge Layer. It does not estimate accuracy and does not treat the absence of evidence as proof that a construct or relationship is absent from source systems.

The projection contains:

- a system-level summary of repositories, observed facts and known limitation occurrences;
- domain summaries for source facts, data-model relationships, physical storage and analysis gaps;
- grouped limitations classified as `unresolved`, `conflicting`, `unsupported`, `not_observed` or `requires_interpretation`;
- explicit count semantics: counts are diagnostic occurrences, not percentages and not unique business elements.

The contract reuses `workspace_missing_fact`, unresolved relationship candidates and canonical relationship storage evidence. It does not create a parallel gap store and does not use LLM interpretation.
