# analysis-ui 2.0.0a88 — Control Plane / Runner boundary

- `runtime/commands.py`, `runtime/jobs.py`, `runtime/pipeline.py`, `runtime/knowledge_contracts.py` — removed UI-owned Producer normalization and direct Core route.
- `runtime/configuration.py`, API models/OpenAPI — removed direct Core command configuration.
- `resources/runtime_contracts/*` — regenerated pinned canonical catalogs.
- `tests/test_control_plane_runner_boundary.py` and affected tests — structural/current contract assertions.
- `pyproject.toml`, `VERSION`, `src/analysis_ui/__init__.py` — version and Assistant dependency alignment.
