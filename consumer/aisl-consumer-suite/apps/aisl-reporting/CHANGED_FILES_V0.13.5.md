# Changed files in 0.13.5

## Runtime

- `pyproject.toml`
- `aisl_reporting/version.py`
- `aisl_reporting/pipeline.py`
- `aisl_reporting/profiles/common/__init__.py`
- `aisl_reporting/profiles/common/v1/__init__.py`
- `aisl_reporting/profiles/common/v1/editorial-policy.md`

## Report contracts and prompts

- `aisl_reporting/profiles/data_model_report/v1/report-contract.yaml`
- `aisl_reporting/profiles/data_model_report/v1/renderer-prompt.md`
- `aisl_reporting/profiles/foreign_data_persistence/v1/report-contract.yaml`
- `aisl_reporting/profiles/foreign_data_persistence/v1/renderer-prompt.md`
- `aisl_reporting/profiles/git_change_impact/v1/report-contract.yaml`
- `aisl_reporting/profiles/git_change_impact/v1/renderer-prompt.md`
- `aisl_reporting/profiles/reference_data/v1/report-contract.yaml`
- `aisl_reporting/profiles/reference_data/v1/renderer-prompt.md`
- `aisl_reporting/profiles/sql_source_inventory_report/v1/report-contract.yaml`
- `aisl_reporting/profiles/sql_source_inventory_report/v1/renderer-prompt.md`
- `aisl_reporting/profiles/system_description/v1/report-contract.yaml`
- `aisl_reporting/profiles/system_description/v1/renderer-prompt.md`
- `aisl_reporting/profiles/workspace_interaction/v1/report-contract.yaml`
- `aisl_reporting/profiles/workspace_interaction/v1/renderer-prompt.md`

## Dataset blueprint metadata

- `aisl_reporting/profiles/sql_source_inventory_report/v1/builder.py`
- `aisl_reporting/profiles/system_description/v1/builder.py`

Изменены только имена и порядок требуемых отчётных разделов. Evidence selection и dataset schemas не менялись.

## Tests

- `tests/test_common_reporting_policy.py`
- `tests/test_pipeline_soft_validation.py`
- `tests/test_system_description_profile_contract.py`
- `tests/test_workspace_interaction_prompt_contract.py`

## Delivery metadata

- `RELEASE_NOTES_V0.13.5.md`
- `CHANGED_FILES_V0.13.5.md`
- `TEST_STATUS_REPORTING_POLICY_V0.13.5.md`
- `SOURCE_TREE_MANIFEST.sha256`
