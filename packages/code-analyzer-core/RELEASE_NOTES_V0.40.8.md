# code-analyzer-core 0.40.8

## Iteration 31 — signature-aware method calls

- Preserves every source-declared Java overload during traceability extraction instead of silently overwriting earlier method bodies under the legacy `Type.method` identity.
- Adds deterministic `caller_operation_signature` and `callee_operation_signature` to method-call facts and `compact/method_calls.json`.
- Uses exact identifier argument types to select a unique overload when source declarations prove the match.
- Retains all same-arity overload candidates with `overload_resolution=ambiguous_same_arity` when source-only evidence cannot select one.
- Keeps legacy operation IDs for existing operation-level consumers.

No application-, package-, class-, or field-specific rules were added.
