# Changed files — knowledge-control-plane 1.2.0a22

- `src/knowledge_control_plane/runtime/process.py`
  - direct-child status polling independent from inherited pipe EOF;
  - bounded stdout/stderr drain;
  - explicit warning and owned process-group descendant termination when inherited output pipes remain open.
- `src/knowledge_control_plane/runtime/jobs.py`
  - one explicit Runner artifact scan after execution-result validation;
  - scan moved off the event loop with `asyncio.to_thread`;
  - runner stage succeeds only after artifact scan/registration.
- `tests/test_process_observability.py`
  - regression for direct process exit with descendant-held pipes;
  - regression for timeout/process-group termination.
- `tests/test_module_baseline.py`
  - version assertion synchronized with release version.
- `VERSION`, `pyproject.toml`, `src/knowledge_control_plane/__init__.py`
  - version `1.2.0a22`.
- `RELEASE_NOTES_V1.2.0a22.md`, `CHANGED_FILES_V1.2.0a22.md`, `TEST_STATUS_V1.2.0a22.md`
  - release provenance.
