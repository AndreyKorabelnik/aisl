# knowledge-layer-core 0.51.0

This release stabilizes SQL Source Inventory around user-facing source tables.

Relations are classified as:

- `external_source`;
- `internal_intermediate`;
- `output_target`;
- `external_or_shared_intermediate`;
- `unknown`.

The default `business_sources` view hides internal intermediates, probable repository-owned staging objects and local output targets. Full facts remain stored and queryable through `technical` and `all` views.

A name containing `tmp`, `temp`, `stg`, `interim` or similar never hides a table by itself. The classifier also requires lifecycle, dependency or repository-owned namespace evidence. A read-only table such as `vendor_stg.customer` remains an external source when no local ownership is observed.
