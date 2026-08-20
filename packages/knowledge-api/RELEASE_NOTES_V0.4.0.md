# knowledge-api 0.4.0

Iteration 22 publishes `data_model_api/v3` and maps the canonical KLC relationship model without legacy relationship fields.

- logical identity/version and physical storage keys are separate;
- target aliases and encoding inputs are explicit;
- physical and logical relationships share one nested schema;
- `target_field`, `target_key_fields`, `join_guidance` and top-level `reference_encoding` are removed;
- the OpenAPI snapshots and all internal consumers are updated together.
