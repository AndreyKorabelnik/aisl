# code-analyzer-core 0.43.17

## Canonical confirmation status for source-to-storage lineage

`source_to_storage_lineage` now publishes one consistent canonical status derived
from the strict evidence maturity dimensions.

When all applicable dimensions are confirmed:

- `lineage_status` is `confirmed`;
- `missing_links` is empty;
- `source_to_storage_segment.status` is `confirmed`;
- `source_to_storage_segment.field_mapping_status` is `confirmed`;
- inline field mappings use `mapping_status=confirmed`.

Candidate navigation markers are no longer retained as unresolved links after the
same path has been fully proven. Partial paths remain unresolved and are not
upgraded.

The compact `source_to_storage_lineage.json` contract now includes the canonical
`lineage_status` field.
