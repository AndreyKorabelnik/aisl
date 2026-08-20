# Changed Files — 0.54.1

- `knowledge_layer_core/materialization_runtime.py` — generic KLC runtime registry, request validation, dispatch, result and knowledge-artifact registration.
- `knowledge_layer_core/materialization_runtime_cli.py` — generic CLI over the same runtime boundary.
- `knowledge_layer_core/materialization_contracts.py` — declares the runtime contract and registered materializations.
- `knowledge_layer_core/__init__.py`, `knowledge_layer_core/version.py`, `pyproject.toml` — public exports, version and CLI entry point.
- `tests/test_materialization_runtime.py`, `tests/test_materialization_contracts.py` — generic runtime and contract tests.
