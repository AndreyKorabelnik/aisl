# Test status — iteration 71 core, corrected 0.43.1

- Focused tests: 6 passed (`physical_model_artifact` and package version consistency).
- `compileall`: passed.
- Real PDM smoke: passed on `CDO_B2C_PDM - ag 20260710.pdm`.
- Extracted: 522 tables, 11,940 columns, 498 keys, 370 relationships, 0 extraction gaps.
- All emitted fact IDs are checked for uniqueness before publication.
- Full unrelated Java/SQL regression was not run; production SQL resolver code was not changed.
