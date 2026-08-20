# Test status — code-analyzer-core 0.43.21

## Scope

Targeted validation only. Runtime repository analysis was not changed, therefore the full Core regression was intentionally not executed.

## Completed checks

- New Core Analysis Catalog tests: 5 passed.
- Targeted Core tests covering profile composition, external profile loading, lightweight CLI and package version consistency: 15 passed in total.
- Clean self-contained source ZIP: the same 15 targeted tests passed.
- Catalog parity with the previous Runner diagnostic: 14 resolved profiles and 48 stage IDs matched.
- Python `compileall`: passed.
- Source-tree manifest verification: passed.
- Wheel build with local build environment: passed.
- Wheel installation and catalog smoke: passed (`0.43.21`, 14 profiles, 48 stages).

## Full regression

Not run. This iteration adds a read-only catalog and CLI command and does not change analysis execution, evidence extraction or output materialization.

## Known limitations

- The stage contract resource describes current behavior but does not yet orchestrate or validate runtime execution.
- SQL and spec stage lists remain declarative labels over fixed runtime pipelines.
- Current Core knowledge-materialization candidates remain in place; no Core/KLC ownership transfer is included in this release.
- Runner still uses its own diagnostic catalog until a later integration step switches it to `core_analysis_catalog/v1`.
