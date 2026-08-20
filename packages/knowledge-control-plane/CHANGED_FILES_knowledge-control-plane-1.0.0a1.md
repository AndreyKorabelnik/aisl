# Changed files — Knowledge Control Plane 1.0.0a1

Breaking rename of active product surfaces from `analysis-ui` 2.0.0a94 to `knowledge-control-plane` 1.0.0a1.

Changed active source/tests/scripts/docs/frontend metadata include:
- `src/knowledge_control_plane/**` (renamed from the previous Python package and updated imports/runtime identifiers)
- `pyproject.toml` (distribution/package data/CLI identity and version)
- `VERSION`
- `README.md`, `config/README.md`, current architecture/API docs
- `frontend/package.json`, `frontend/package-lock.json`, current frontend strings/identifiers
- tests and current validation scripts referencing the active product name
- regenerated `docs/api/generic-v1.openapi.json`
- regenerated `SOURCE_TREE_MANIFEST.sha256`

Historical release/test/change documents remain unchanged as provenance.
No compatibility alias or old-name runtime fallback was added.
