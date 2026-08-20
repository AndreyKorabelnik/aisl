# Analysis UI 2.0.0a80

## Changes
- Restored FDP as a declarative Knowledge Profile, not as the removed legacy FDP pipeline.
- Stable context: one repository.
- Product: `persistence-lineage`.
- Report: `foreign-data-persistence-report/v1`.
- Chat policy: `foreign-data-persistence/v1`.
- The master uses the existing generic knowledge execution/publication/chat runtime.

## Validation
- Full Python suite: 81 passed.
- Real producer plan remains the generic two-node persistence-lineage plan.
