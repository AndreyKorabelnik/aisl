# AISL Storage Join Semantics — Acceptance

Date: 2026-08-19

## Accepted behavior

1. A declared relationship can receive storage-level join semantics without a PDM when published code/XML-derived storage evidence is sufficient.
2. Exact structural equivalence between an observed source reference expression and observed target storage identity yields:
   - `status=strongly_supported`
   - `join_readiness=executable_storage_join`
   - `match_basis=exact_structural_expression_signature`
3. The result remains derived knowledge and does not assert a physical SQL/PDM join.
4. Multiple relationships using one source field remain separate relationship occurrences.
5. Multiple incompatible candidates remain `ambiguous`; no candidate is silently selected.
6. Missing correspondence evidence remains `unresolved/not_ready`.
7. Existing attribute-extension correspondence code uses the same shared structural matcher; no second matcher exists.
8. Compact consumer JSON preserves `relationships[]` and removes repeated audit-only detail from the default representation.
9. Full provenance remains available through detail/provenance mode and AISL evidence APIs.

## Real UCP baseline already confirmed by user before this change

The previous canonical (`aisl-producer 0.3.1`, `aisl-server 0.3.2`) completed the real UCP bundle-v2 path on the user's machine:

UCP sources → Producer → publication bundle v2 → Server import → immutable revision → aisl-client `data-model-object(Individual)`.

Observed consumer result:

- `storage_context.status=available`
- `common.model-storage-semantics` published
- `common.logical-storage-mapping` published
- 41 relationships
- 33 ambiguous relationships
- 0 physical joins confirmed

This closes the previous bundle-v2 end-to-end acceptance gap.

## Pending real acceptance for this change

A real UCP revision using `logical-storage-model-mapping/v2` has not yet been produced on the user's machine. The next real acceptance is to rebuild/import and verify that exact cases such as `Individual.birthCountry → Country` become `strongly_supported + executable_storage_join` when the published expression evidence matches, while ambiguous cases remain ambiguous.
