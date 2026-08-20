# Test status — iteration 36

- Python compileall: passed.
- Interaction graph suite: 20 passed.
- Other tests excluding `test_workspace_data_model.py`: 121 passed, 13 skipped.
- Total: 141 passed, 13 skipped.
- New regressions verify:
  - service identity selects the correct target among identical HTTP paths;
  - identical method/path without address evidence remains ambiguous and creates no edge;
  - indexed lookup reports one candidate while two target routes exist;
  - boundary inventory preserves authority and service identity;
  - strict islands do not join ambiguous candidates.

Known test limitation: `test_workspace_data_model.py` was not rerun because it has repeatedly exceeded the available process timeout in prior iterations and the changed HTTP interaction contour does not modify data-model materialization.
