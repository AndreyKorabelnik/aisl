# Changed files — static-analysis-runner 0.9.56

## Removed

- `static_analysis_runner/physical_model.py` — obsolete Runner-owned PDM wrapper.
- `static_analysis_runner/knowledge_layer.py` — hidden Task/Suite compatibility materialization entrypoint.
- `tests/test_knowledge_layer_materialization.py` — tests for the removed compatibility route.

## Changed

- `static_analysis_runner/cli.py` — removed `physical-model` and hidden `materialize-knowledge-layer` commands.
- `tests/test_physical_model_pipeline.py` — now proves the typed `physical-model/v1 → knowledge-execute → KLC physical-model` route.
- `tests/test_cli.py`, `README.md`, `docs/CLI.md`, version metadata.
