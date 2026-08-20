# static-analysis-runner 0.10.16

Architecture Boundary Simplification — Control Plane input normalization.

- Added `knowledge-input-prepare` as the Runner-owned boundary for raw execution context.
- Runner now owns deterministic conversion of a raw PowerDesigner `.pdm` into the typed `physical-model/v1` input by invoking Core.
- Runner now owns normalization of all Prepared Knowledge artifacts from immutable published-revision snapshots.
- Product-specific selection remains in the existing execution planner; input preparation does not guess which artifact is needed.
- Existing `knowledge-input-inventory` remains the lower-level typed-input command; no compatibility adapter or second execution route was added.
