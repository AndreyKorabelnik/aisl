# Changed files — 0.9.43

- `static_analysis_runner/knowledge_planning.py` — user-facing `knowledge_catalog/v1`, `knowledge_profile/v1` validation, deterministic `knowledge_resolution_plan/v1`, current-vs-target availability and source lineage to Core stages/Foundation.
- `static_analysis_runner/cli.py` — new read-only `knowledge-catalog` and `knowledge-profile-resolve` commands.
- `tests/test_knowledge_planning.py` — catalog/profile/resolver validation, determinism, scope, dependency, current/target availability and CLI tests.
- `schemas/knowledge_profile_v1.schema.json` — machine-readable user profile contract without Task/Suite/Core technical identifiers.
- `examples/knowledge-profiles/client-workspace.yaml` — example workspace knowledge profile.
- `docs/KNOWLEDGE_PLANNING.md` — ownership, contracts, current limitations and revised next steps.
- `README.md`, `docs/CLI.md` — command usage.
- `pyproject.toml`, `static_analysis_runner/version.py`, `tests/test_cli.py` — version 0.9.43.
