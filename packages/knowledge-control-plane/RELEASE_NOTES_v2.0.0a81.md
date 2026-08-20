# Analysis UI 2.0.0a81

## Reference Data / own NSI knowledge profile

- Added `reference-data-v1` as a declarative 1..N repository workspace profile.
- Uses existing `reference-data` production, `reference-data-report/v1` and `reference-data/v1` Assistant policy.
- The wizard selects stable repository context only; it does not collect candidate NSI names or perform semantic classification.
- No scenario-specific execution runtime was introduced.
