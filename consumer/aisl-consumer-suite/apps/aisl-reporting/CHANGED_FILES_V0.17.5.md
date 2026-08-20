# Changed files — 0.17.5

- `aisl_reporting/profiles/workspace_interaction/v1/builder.py`
  - factor compact path formatting;
  - add bounded target-local continuation for selected journey cards;
  - preserve continuation confidence, gaps, branches and evidence separately.
- `aisl_reporting/profiles/workspace_interaction/v1/renderer-prompt.md`
  - require target-local continuation to be rendered separately when available.
- `tests/test_workspace_interaction_target_continuation.py`
  - deterministic path-selection and gap-preservation tests.
- `tests/test_workspace_interaction_prompt_contract.py`
  - target-local continuation rendering contract.
- `aisl_reporting/version.py`, `pyproject.toml`
  - version 0.17.5.
