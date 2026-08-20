# code-analyzer-core 0.44.23a1

S2T evidence completeness increment. The analyzer remains an observed-evidence producer.

## Changes
- Preserve DSL calls nested inside control-flow statements (for example `historicity(...)`) as typed `sql_script_call` syntax facts.
- Include repository config files explicitly referenced by observed DSL calls/paths in SQL workflow binding extraction; unrelated config remains excluded.
- Evaluate only exact file-local string concatenations made of quoted literals and already-observed local scalar bindings.
- Expand those exact local SQL-fragment bindings before scoped SQL parsing while preserving the original statement as evidence and linking derived scoped facts back to the concrete `sql_script_binding_id` used.
- Preserve runtime/workflow placeholders that cannot be resolved from exact preceding file-local bindings; no runtime values are guessed.

## Scope discipline
No business meanings, target/source relationships, Gold rows, table-specific rules or application-specific aliases are introduced.
