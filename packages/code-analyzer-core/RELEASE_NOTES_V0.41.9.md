# Release notes — code-analyzer-core 0.41.9

Iteration 56 adds canonical branch-aware bindings from CTE and derived relation references to the SELECT scopes that define them.

## Changes

- Replaced the legacy scalar `source_scope_id` on scoped relation facts with canonical `source_scope_ids`.
- Added `definition_status` for intermediate relations: `resolved` or `unresolved`; physical relations use `not_applicable`.
- CTE references are resolved through SQLGlot lexical scopes, preserving nested CTE shadowing.
- Derived relations are linked to their defining output SELECT scopes.
- `UNION`, `INTERSECT`, and `EXCEPT` definitions preserve every output branch rather than selecting one arbitrarily.
- Parenthesized/subquery-wrapped set operations are unwrapped before branch collection.
- Added a conservative AST-name fallback for a uniquely named CTE when lexical scope analysis cannot be produced; ambiguous/shadowed names are never guessed.
- Added run diagnostics for resolved/unresolved intermediate relations and total definition branches.
- Updated navigation previews to expose `source_scope_ids` and `definition_status`.
- SQL profile schema version advanced from `0.9` to `1.0` because the canonical scoped-relation contract changed.
- Package and runtime versions are synchronized at `0.41.9`.

## Compatibility

No compatibility adapter is provided. Consumers must read `source_scope_ids`; the removed scalar `source_scope_id` is not emitted.

This iteration does not yet recursively traverse intermediate fields. It establishes the branch-aware definition graph required for that traversal.
