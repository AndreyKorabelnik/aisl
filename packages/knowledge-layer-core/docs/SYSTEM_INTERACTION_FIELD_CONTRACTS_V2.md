# System interaction field contracts v2

`system_interaction_field_contract` is the deterministic field-level bridge between an already
matched HTTP boundary interaction and the canonical repository value-flow graph.

The mart publishes three evidence classes:

1. `exact_wire_path` — one normalized request path occurs exactly once in both compact contracts;
2. `exact_observed_nested_boundary_path` — the source compact contract is shallow, but core
   publishes one exact operation-scoped outbound boundary occurrence matching a target wire path;
3. `exact_collection_member_builder_path` — an exact `stream().map(methodReference)` binding,
   nested builder composition, direct flow to the outbound boundary, and a target wire path jointly
   reconstruct a collection-member field.

Reconstructed contracts remain `probable`. They do not promote the containing boundary
interaction. Their payload includes the source occurrence, method-reference/builder evidence,
field-flow edge records, reconstruction basis, and target contract evidence.

Execution context is optional and is never a gate. Without it, reconstruction requires a direct
observed field-flow path from the composed nested object to the outbound boundary occurrence.

Normalization is intentionally narrow:

- comparison is case-insensitive;
- `[]` collection-member markers are removed;
- slash and repeated-dot separators are canonicalized to `.`.

The materializer does not perform fuzzy name matching, synonym inference, leaf-name matching, or
business-semantic identity. Ambiguous structural candidates are not published.

Schema version: `workspace_system_interaction_field_contract/v2`.
Capability: `workspace.system-interaction-field-contracts`.
