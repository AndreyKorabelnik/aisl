# knowledge-layer-core 0.51.1

Validation-only release for SQL Source Inventory v1.

## Added

- Curated 30-file quality fixture for `datamart_profile_fl`.
- Reusable `knowledge_layer_core.sql_inventory_quality` evaluator.
- Relation precision/recall, semantic-role accuracy, field precision/recall, field-role accuracy, column-resolution metrics.
- Source SHA-256 pinning for every reviewed SQL file.
- JSON and Markdown quality reports with target gates and per-file failures.

## Baseline result

- Relation precision: 1.0000.
- Relation recall: 0.8957.
- Semantic classification accuracy: 1.0000.
- Field precision/recall on 11 exact relation checks: 1.0000 / 1.0000.
- Field-role accuracy: 1.0000.
- Column resolution rate across the selected files: 0.9391.
- 28 of 30 files pass all curated expectations.

The two failing files expose 17 missing relations and define the next core work. No production query or materialization behavior changed.
