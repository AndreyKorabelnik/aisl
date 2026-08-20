# knowledge-layer-core 0.59.2

Restores the typed KLC-to-KLC `interaction-field-contracts` materialization that was disconnected during Task/Suite runtime removal.

- accepts `repository_value_flow/v6` from `repository-value-flow`;
- accepts `workspace_system_interaction/v6` from `system-interactions`;
- reuses the existing deterministic `materialize_system_interaction_field_contracts` logic;
- publishes `workspace_system_interaction_field_contract/v2`;
- does not restore Task/Suite, topology, fallback, or dual-write.

Transport value-flow enrichment is the next step and is intentionally not included in this release.
