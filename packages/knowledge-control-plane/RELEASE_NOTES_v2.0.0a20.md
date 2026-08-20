# analysis-ui 2.0.0a20

Iteration 24.2 removes the unsupported source-tree `backend/` runtime.

- `src/analysis_ui` is now the only server implementation.
- pytest, compilation, manifests and check scripts target only the installed runtime.
- obsolete route-migration metadata was removed from OpenAPI.
- historical backend baseline files and recovery artifacts were removed.
- frontend behavior is unchanged in this checkpoint.
