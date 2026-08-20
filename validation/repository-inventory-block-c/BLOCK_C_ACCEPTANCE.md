# Repository Inventory Block C acceptance

Status: PASS for bounded productization acceptance. Full framework regression was not run.

## Scope

Block C productizes the already accepted repository-scoped `repository-inventory/v2` materialization. It adds no analyzer, materializer, parser or evidence-production policy.

## Product/catalog

- Runner official Knowledge Product: `repository-inventory`.
- Scope: `repository`.
- KCP built-in profile: `repository-inventory-v1`.
- KCP one-shot scenario: `build-repository-inventory-v1`.
- Final pinned Runner knowledge catalog: 18 knowledge products, 0 uncatalogued materializations.

## Read API

Revision-bound read-only endpoints under `/api/knowledge/v1/systems/{system_id}/repository-inventory`:

- summary / identity;
- coverage;
- technologies;
- concepts;
- interfaces;
- inputs;
- outputs;
- structural families;
- UNCLASSIFIED candidates;
- diagnostics.

Knowledge API does not inspect repositories and does not implement Inventory semantics. It reads the canonical published KLC artifact through Prepared Knowledge Runtime queries.

## Targeted tests

Final focused set: 11/11 PASS.

Coverage includes Runner product catalog, KCP one-shot profile/scenario, pinned catalog parity, Runner metadata projection, Repository Inventory HTTP API including Bitbucket URL and coverage, explicit 409 for a malformed/non-canonical Inventory artifact, OpenAPI parity, and version baselines.

## Not run

- Full framework regression: NOT RUN by request and not required for this productization-only block.
- Re-analysis of UCP/AT900/gateway: NOT RUN because Block C changes product/catalog/read boundaries only; B.5 already measured the unchanged producer/materialization path.
