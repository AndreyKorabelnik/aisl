# Changed files — Knowledge Control Plane 1.2.0a17

- `src/knowledge_control_plane/cli.py` — `run --bitbucket-project-url` high-level repository-batch source; single-run `--system-id` remains required only outside batch mode.
- `src/knowledge_control_plane/runtime/repository_batch_run.py` — scenario/profile-to-Runner repository-batch orchestration using temporary profile serialization and pinned catalogs.
- `src/knowledge_control_plane/runtime/knowledge_contracts.py` — shared canonical Knowledge Profile serializer.
- `tests/test_repository_batch_cli.py` — high-level batch routing/scope/cleanup contract tests.
- `tests/test_module_baseline.py`, `README.md`, version metadata — release baseline and CLI documentation.
