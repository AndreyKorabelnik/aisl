# Changed files — Knowledge Control Plane 1.2.0a1

Relative to the delivered 1.1.0a1 backend checkpoint, the final block primarily changes:

- `frontend/src/views/Productions.vue` (new)
- `frontend/src/services/types.ts`
- `frontend/src/services/api.ts`
- `frontend/src/router/index.ts`
- `frontend/src/App.vue`
- `src/knowledge_control_plane/runtime/app.py`
- `src/knowledge_control_plane/runtime/productions.py`
- `src/knowledge_control_plane/runtime/freshness.py`
- `src/knowledge_control_plane/runtime/routes.py`
- `tests/test_production_refresh_ui.py` (new)
- `tests/test_auto_refresh.py`
- version, OpenAPI, release/test metadata and source manifest

The 1.1.0a1 backend Production Registration/source snapshot/pinned-acquisition implementation is retained unchanged except for the final generic profile compatibility and explicit force-refresh semantics described in the release notes.
