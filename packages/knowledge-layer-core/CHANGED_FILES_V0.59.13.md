# knowledge-layer-core 0.59.13

## Purpose
Allow strict cross-workflow field lineage when workflow orchestration explicitly proves producer→consumer dependency.

## Changes
- Cross-artifact schema v3 adds `cross_artifact_workflow_dependency`.
- Workflow dependency is derived only from observed `entities` and `trigger` bindings with exact normalized entity identity.
- Unique producer: `derived/matched` and eligible for lineage traversal.
- Multiple producers for the same identity: `candidate/ambiguous`; not used for traversal.
- Same-workflow materialization remains preferred; otherwise only nearest proven upstream workflow producers are considered.
- End-to-end lineage stores workflow dependency provenance.
