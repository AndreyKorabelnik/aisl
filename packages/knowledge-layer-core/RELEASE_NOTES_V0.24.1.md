# knowledge-layer-core 0.24.1

Adds a facts-only developer diagnostic for storage-key and reference-encoding evidence.

## Changes

- Adds `knowledge_layer_core.relationship_diagnostics` with a read-only diagnostic API and CLI.
- Separately reports logical identity, observed builder key assignments, alias assignments,
  return-to-reference value flow, logical-key correspondence, polymorphic targets and encoding semantics.
- Detects the current scope-insensitive local result-binding ambiguity without resolving it by guesswork.
- Refuses to infer alias normalization, type-prefixed encoding, a physical key field or a SQL join.
- Supports ordinary, collection and polymorphic relationship observations without package, class or field-name rules.
- Adds generic runtime tests plus real UCP validation artifacts. UCP is validation data only and does not affect implementation logic.

This version does not change the workspace schema, relationship materialization or public data-model JSON.
