# Release notes — knowledge-api 0.10.1

Version 0.10.1 exposes practical SQL Source Inventory coverage as a first-class API contract.

## Changes

- Added typed `coverage.source_inventory` to the SQL relations response.
- Consumers no longer need to parse raw `repositories[].coverage_json`.
- The compact block includes source-field candidate, resolved and unresolved counts, resolution rate, non-source values, limitation categories and policy.
- Updated dependency to `knowledge-layer-core>=0.51.2,<1.0.0`.
- Regenerated canonical OpenAPI.

## Real repository result

For `datamart_profile_fl`, the endpoint reports:

- 11,061 source-field candidates;
- 10,694 resolved source fields;
- 367 unresolved source fields;
- 96.682% source-field resolution;
- 365 ambiguous unqualified fields;
- 2 relation-unavailable fields;
- 151 semantic parameters and 27 generated fields reported separately.
