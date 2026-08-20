# Release notes — knowledge-layer-core 0.51.2

Version 0.51.2 aligns SQL Source Inventory coverage with the canonical source-field policy.

## Changes

- Generated LATERAL/EXPLODE values no longer count as resolved source-table fields.
- Semantic parameters and projection outputs remain separate non-source categories.
- `status` is now `partial` when genuine unresolved source-field candidates remain.
- Added an explicit coverage policy string.
- No database schema or SQL fact contract changed.

## Real repository result

On `datamart_profile_fl`:

- total column usages: 11,239;
- source-field candidates: 11,061;
- resolved source fields: 10,694;
- unresolved source fields: 367;
- resolution rate: 0.966820;
- semantic parameters: 151;
- generated fields: 27;
- limitations: 365 ambiguous unqualified fields and 2 relation-unavailable usages.
