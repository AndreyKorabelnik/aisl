# Changed files — 0.17.4

- `aisl_reporting/profiles/workspace_interaction/v1/builder.py`
  - derive technical repository summaries from canonical boundary/match/diagnostic records;
  - keep optional published coverage statuses separate;
  - use observed summaries for role candidates and diagram nodes;
  - use canonical observed counts in coverage summary;
  - cap journey budgets at 2/4/5.
- `aisl_reporting/profiles/workspace_interaction/v1/renderer-prompt.md`
  - restore representative journey balance to ~20–30%, maximum one third of main text.
- `tests/test_workspace_interaction_observed_summary.py`
  - regression tests for reporting without the interaction-coverage mart and journey budget.
- `tests/test_rich_report_contracts.py`
  - updated canonical workspace-interaction journey budgets.
- `aisl_reporting/version.py`, `pyproject.toml`
  - version 0.17.4.
