# aisl-reporting 0.3.0

## Added

- `workspace-interaction/v1` report product.
- Deterministic workspace dataset builder using only public KLC query services.
- Repository composition and role observations.
- Complete cross-repository type/configuration correspondences.
- Diagram-ready structural edges, partial journey candidates, gaps, and exact evidence index.
- Explicit distinction between structural evidence and runtime interaction evidence.

## Migration result

The UCP data-model workspace passes a structural workspace migration gate. A complete old/new runtime-interaction A/B comparison is intentionally left open because this fixture contains no system-interface profile facts and the legacy profile refuses to run without its old interface-tool catalog.

No fake legacy result or fabricated runtime interaction was introduced to force parity.

## Validation

- 9 passed, 0 failed.
- Real UCP dataset: 2 repositories, 403 model objects, 1,186 cross-repository correspondences, 225 exact evidence references.
- Generated report: all 12 required sections, 12 valid evidence citations, 0 unknown evidence IDs.
