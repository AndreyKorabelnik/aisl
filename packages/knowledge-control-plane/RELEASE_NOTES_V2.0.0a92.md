# analysis-ui 2.0.0a92

Final ownership cleanup after Architecture Boundary Simplification.

- Knowledge execution snapshots no longer duplicate Runner defaults (`include_optional_sources` / `minimum_coverage`). Analysis UI submits only the selected `knowledge_id`; Runner owns option defaults and validation.
- Pinned runtime catalogs regenerated from Core 0.44.22, KLC 0.59.49 and Runner 0.10.17.
- No production semantics, dependency resolution or materialization rules are owned by Analysis UI.
