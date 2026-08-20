# Changed files — 0.12.1

- `workspace_interaction/v1/builder.py`: removed repository-island queries and fields; added mandatory journey-card contract.
- `workspace_interaction/v1/renderer-prompt.md`: made every selected attribute journey mandatory and removed island content.
- `workspace_interaction/v1/report-dataset.schema.json`: added `required_card_count` and `required_wire_paths`.
- `validation.py`: validates that every selected journey appears in Markdown.
- Updated profile contracts, tests and release metadata.
- `aisl_reporting/validation.py` — report findings are warning-only.
- `aisl_reporting/pipeline.py` — removed strict report-validation failure path.
- `aisl_reporting/cli.py` — removed `--strict-validation` and red validation-error status.
- `tests/test_report_validation.py`, `tests/test_pipeline_soft_validation.py` — warning-only contract tests.
