# knowledge-layer-core 0.52.1

Corrects the default `SQL Source Inventory v1` export boundary.

- `export_sql_source_inventory()` now includes only `physical` and `physical_template` relations when `relation_kind` is not explicitly supplied.
- Visible CTE, derived or unknown relation kinds remain queryable via `list_sql_relations()` but are not exported as external sources.
- The real datamart export now contains 201 source relations and 1,478 used fields.
