# Concept Layer Removal — Test Status

Date: 2026-08-17

Final / authoritative results:
- KLC final version `0.61.0a38`: 257 PASS / 8 SKIP (completed independent batches).
- Prepared Knowledge Runtime final version `0.1.0.post12`: 12/12 PASS.
- Knowledge API: 118/118 PASS after functional cleanup; after version bump to `0.37.0` and official OpenAPI regeneration, affected Repository Inventory/Portfolio/OpenAPI gate 15/15 PASS.
- Knowledge Control Plane final version `1.2.0a30`: 95/95 PASS.
- Real UCP forced-rebuild publication: PASS.
- Real datamart forced-rebuild publication: PASS.
- Machine structural/API acceptance: PASS.

Unchanged byte-identical packages:
- Core `0.44.23a7`: authoritative inherited regression 610/610 PASS.
- Runner `0.10.27`: authoritative inherited regression 113/113 PASS.

Timeout discipline:
- monolithic KLC/API runs that hit the execution limit were not counted as PASS;
- KLC was rerun in completed batches;
- API was rerun file-by-file to an aggregate 118/118 before the final version-only bump.
