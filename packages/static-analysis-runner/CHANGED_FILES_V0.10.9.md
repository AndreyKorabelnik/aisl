# Changed files — static-analysis-runner 0.10.9

- `static_analysis_runner/resources/knowledge-product-catalog.v1.json`
  - maps user-facing `data-model-attribute-extension` to KLC `data-model-attribute-extension-context`;
  - classifies `cross-artifact-data-model-mapping` as an internal technical dependency;
  - updates product content/summary to the agent-ready technical join-semantics contract.
- `tests/test_knowledge_planning.py`
  - updates the KLC contract fixture with the new materialization;
  - validates recursive closure through storage -> logical/storage -> cross-artifact -> attribute-extension context.
- `static_analysis_runner/version.py`, `pyproject.toml`
  - version raised to 0.10.9.
- release/test metadata for this checkpoint.
