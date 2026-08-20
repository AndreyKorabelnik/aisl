# Changed files — static-analysis-runner 0.10.8

- `static_analysis_runner/knowledge_planning.py`
  - enriches internal materialization catalog entries from KLC contracts;
  - recursively closes required internal materialization dependencies in knowledge resolution;
  - carries required evidence/model inputs and explicit internal dependency diagnostics into the technical plan.
- `static_analysis_runner/resources/knowledge-product-catalog.v1.json`
  - adds `data-model-attribute-extension`;
  - classifies three current KLC materializations as internal technical dependencies.
- `tests/test_knowledge_planning.py`
  - updates KLC fixtures to current materializations;
  - validates the new catalog shape and generic internal dependency closure.
- `static_analysis_runner/version.py`, `pyproject.toml`
  - version raised to 0.10.8.
