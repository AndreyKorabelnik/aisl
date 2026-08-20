# knowledge-layer-core 0.21.0

## Purpose

Hardens the shared consumer query layer for multi-repository reporting and grounded assistant tools.

## Changed

- `ReportingQueryService` now emits portable source paths instead of paths rooted in the machine that produced the Knowledge Layer.
- `DataModelQueryService.get_cross_repository_correspondences` paginates the complete candidate catalogs and returns only genuine cross-repository observations.
- Local same-repository resolution candidates are no longer mixed into workspace correspondence results.
- Query result ordering and evidence envelopes remain deterministic.

## Real UCP validation

- 1,186 cross-repository correspondences returned.
- 324 configuration/type correspondences.
- 862 type-reference resolutions.
- 0 same-repository observations in the cross-repository result.
- Maven and source evidence paths are portable workspace-relative paths.

## Validation

- 138 passed, 5 skipped, 0 failed.
- The two historically long combined-process files were also executed in isolated batches; all 38 contained tests passed.
