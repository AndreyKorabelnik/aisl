# Release notes — code-analyzer-core 0.42.6

Version 0.42.6 makes SQL Source Inventory coverage actionable without changing extracted facts.

## Changes

- Added `column_usages.source_inventory` to `sql-analysis/v1` coverage.
- Semantic parameters are reported separately and no longer reduce source-field resolution.
- Generated `LATERAL VIEW` / `EXPLODE` values are reported separately and no longer reduce source-field resolution.
- Genuine ambiguity and missing relation context remain explicit unresolved source-field categories.
- Existing overall `analysis_status` and all canonical fact types remain unchanged.
- SQL profile implementation version is now `1.7`.

## Real repository effect

On `datamart_profile_fl`:

- total observed column usages: 11,239;
- source-field candidates: 11,061;
- resolved source-field usages: 10,694;
- unresolved source-field usages: 367;
- practical source-field resolution rate: 0.966820;
- ambiguous unqualified fields: 365;
- relation unavailable: 2;
- semantic parameters reported separately: 151;
- generated values reported separately: 27.

The unchanged curated SQL Source Inventory fixture remains fully green: 30/30 cases and 100% relation, classification, field, and role quality gates.
