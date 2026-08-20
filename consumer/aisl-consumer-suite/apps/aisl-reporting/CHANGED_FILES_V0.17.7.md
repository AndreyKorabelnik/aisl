# aisl-reporting 0.17.7 changed files

- `aisl_reporting/profiles/workspace_interaction/v1/builder.py`
  - separates unmatched/ambiguous outbound diagnostics from unmatched inbound operations;
  - groups inbound evidence by technical HTTP operation signature so sibling route/controller evidence is not falsely reported as unmatched;
  - builds a bounded 8–15 question set grounded in observed probable routes, unmatched boundaries, response-contract gaps and partial journeys.
- `aisl_reporting/profiles/workspace_interaction/v1/report-dataset.schema.json`
  - replaces the ambiguous combined unmatched field with explicit outbound and inbound sections.
- `aisl_reporting/profiles/workspace_interaction/v1/renderer-prompt.md`
  - requires separate inbound/outbound negative controls and 8–15 concrete grounded questions.
- `tests/test_workspace_interaction_observed_summary.py`
  - covers duplicate inbound evidence grouping and bounded concrete owner questions.
- `pyproject.toml`, `aisl_reporting/version.py`
  - version 0.17.7.
