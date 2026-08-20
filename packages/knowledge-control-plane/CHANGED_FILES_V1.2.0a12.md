# Changed files — Knowledge Control Plane 1.2.0a12

- `src/knowledge_control_plane/runtime/output_safety.py` — human-readable default analysis output layout and `RUN_INFO.json` receipt writer.
- `src/knowledge_control_plane/runtime/pipeline.py` — supplies stable system/scenario/created-at context to the output-path builder.
- `src/knowledge_control_plane/runtime/jobs.py` — writes and refreshes run receipt without changing job identity or reuse keys.
- `tests/test_knowledge_execution_ui.py` — targeted layout, explicit-output and receipt tests.
- version/release metadata updated to `1.2.0a12`.
