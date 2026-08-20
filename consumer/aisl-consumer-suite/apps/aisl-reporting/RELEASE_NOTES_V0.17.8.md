# AISL Reporting 0.17.8

## Changes
- Aligned `foreign-data-persistence-report/v1` with canonical `persistence-lineage/v1`.
- Replaced obsolete capability requirement `common.foreign-data-persistence` with `workspace.fdp-paths` and `workspace.persistence-lineage`.
- Existing FDP builder remains KLC-query-backed and does not assign a business risk verdict.

## Validation
- Full test suite: 105 passed, 2 skipped.
- Real AT900 dataset: 781 paths, 969 mechanical cases, 8 confirmed exact-field cases; dataset validation passed.
