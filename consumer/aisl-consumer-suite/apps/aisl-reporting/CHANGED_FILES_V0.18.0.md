# Changed files — 0.18.0

- All Knowledge-revision report profiles now consume Knowledge API only.
- Removed direct KLC/DuckDB consumer path and `knowledge-layer-core` runtime dependency.
- `workspace-interaction/v1` now reports active interaction knowledge only. Parked direct value-flow/attribute-path enrichment was removed from this active path.
- Removed obsolete attribute-journey validation/tests and aligned prompt/schema/dataset plan.
