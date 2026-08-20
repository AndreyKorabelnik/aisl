# Release notes — code-analyzer-core 0.41.4

Iteration 51 introduces semantic SQL placeholders and simple local script bindings without building a workflow, environment, or deployment model.

## Changes

- Placeholder identity is preserved in parser input and all public facts; `${...}` is no longer collapsed to `PLACEHOLDER`.
- Schema-qualified templates such as `${$source_schema}.client` are canonical logical relations of kind `physical_template`.
- Global cross-file YAML/CONF value collection was removed to prevent accidental mixing of environments and workflows.
- Added `sql_script_binding` facts for deterministic `let` assignments.
- A prior scalar binding from the same script can resolve a semantic placeholder as `locally_bound`.
- Unresolved schema-only placeholders are treated as `logical_template` and do not block proven column lineage.
- Placeholders affecting a table, target, column, expression, predicate, or JOIN remain explicit `unbound_semantic` diagnostics.
- Partial mart-column lineage is retained instead of discarding an entire statement because one semantic placeholder is unresolved.
- Lineage maturity is evaluated per edge; unrelated unresolved parameters no longer downgrade every edge in the query.
- SQL fragment evidence now records the line of the first actual fragment content after preceding statements.

## Compatibility

No compatibility layer is provided. `sql_placeholder_usage` / global placeholder-resolution semantics are replaced by the canonical `sql_semantic_placeholder` and `sql_script_binding` facts.
