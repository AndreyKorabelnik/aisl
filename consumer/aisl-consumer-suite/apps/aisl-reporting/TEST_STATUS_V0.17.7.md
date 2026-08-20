# Test status — aisl-reporting 0.17.7

Affected reporting tests: **38 passed**.

Test set:
- `test_workspace_interaction_target_continuation.py`
- `test_workspace_interaction_observed_summary.py`
- `test_workspace_interaction_prompt_contract.py`
- `test_rich_report_contracts.py`
- `test_report_validation.py`
- `test_contracts.py`

Additional checks:
- `compileall aisl_reporting`: PASS.
- real four-repository dataset build against KLC 0.59.32: PASS.
- report dataset JSON Schema validation: PASS.
- dangling evidence IDs: 0.

Full reporting regression was not run for this narrow profile-only change.
