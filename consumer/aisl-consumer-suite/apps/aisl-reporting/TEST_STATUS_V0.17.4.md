# Test status — aisl-reporting 0.17.4

## Targeted / affected tests

31 passed:

- `tests/test_workspace_interaction_observed_summary.py`
- `tests/test_workspace_interaction_prompt_contract.py`
- `tests/test_rich_report_contracts.py`
- `tests/test_report_validation.py`
- `tests/test_contracts.py`

## Static validation

- `python -m compileall aisl_reporting`: PASS
- real workspace dataset build: PASS
- real workspace roles: 4
- real workspace diagram nodes: 4
- real workspace detailed journeys: 5

Full project regression was not run for this small reporting-only checkpoint; it is deferred until the larger System Interactions block is ready for baseline/release acceptance.
