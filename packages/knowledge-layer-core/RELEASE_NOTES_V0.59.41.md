# knowledge-layer-core 0.59.41

Legacy Cleanup Block 3 removes the first confirmed behavioral backward-compatibility adapter from the current Knowledge Layer.

## What changed

- `repository-value-flow` now requires canonical `value_flow_evidence_record`; it no longer falls back to generic `analysis_record`.
- `system-interactions` now requires canonical `interaction_boundary_evidence_record`; it no longer falls back to generic `analysis_record`.
- `interaction-field-contracts` consumes the attached typed repository-value-flow relation directly and no longer creates a temporary `analysis_record`.
- The marker `legacy_contract_published=False` was removed rather than retained as a tombstone.
- Old generic-only inputs now fail explicitly.

## Not changed

- uncertainty/diagnostic behavior and normal static-analysis fallbacks;
- current optional typed-mart capability checks;
- `COMPATIBILITY_SCHEMA_VERSION`, `fetch_size`, `legacy_fallback_used`, `legacy_conceptual_model_consumed`; these remain separate audit candidates.
