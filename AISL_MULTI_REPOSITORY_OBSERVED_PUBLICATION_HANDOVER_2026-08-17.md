# Handover — AISL multi-repository observed publication

Date: 2026-08-17
Status: AISL_MULTI_REPOSITORY_OBSERVED_PUBLICATION_FIX_COMPLETE

## Completed

- Fixed Knowledge API observed product slot identity for multi-repository revisions.
- Product replacement identity is source-aware and stable across source revisions.
- True same-source/same-kind duplicates remain rejected.
- Real UCP `build-data-model-v1` with `ucp-api + ucp-tsa-v4` publishes successfully.
- Knowledge API version advanced to 0.37.1.
- Stale Prepared Runtime exact dependency pin removed in favor of the supported 0.1.x range.

## Unchanged semantic producers

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a7
- static-analysis-runner 0.10.27
- knowledge-layer-core 0.61.0a38
- prepared-knowledge-runtime 0.1.0.post12
- knowledge-integration 0.1.15
- knowledge-reporting 0.18.1
- knowledge-control-plane 1.2.0a30
- aisl-contract 0.3.0b8

## Verification

- Targeted observed/AISL persistence: 10/10 PASS.
- Contract/OpenAPI focused: 2/2 PASS.
- Final focused recheck: 3/3 PASS.
- Real multi-repository UCP publication: PASS, revision `rev-cf1820d42ff0cf021ccb358a`.
- Full framework regression not required/run for this isolated Knowledge API change.

## Limitations / migration stance

No backward-compatibility adapter is provided for old observed product slots (`core:<artifact_kind>`). Existing immutable revisions remain readable as published; new publications use source-aware slots. If incremental composition across the old/new slot identity boundary is required, republish a full new baseline revision rather than introducing dual slot semantics.

## Continue from

Use the final canonical ZIP and SHA from the recovery package produced for this block. The next product work should proceed from that canonical, not from the previous `core-structural-inventory` archive.
