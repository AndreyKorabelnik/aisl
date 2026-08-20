# knowledge-layer-core 0.61.0a32

Calibrates useful consumer inference for the existing `data-model-attribute-extension-context/v1` product without creating a second producer/read path.

Each relationship keeps its original evidence-level `confidence`; `basis.usefulness` now separately states what a consumer may safely do with that evidence:

- exact observed SQL relationship -> `confirmed` / reuse observed JOIN;
- confirmed reference/key encoding without exact SQL -> `strongly_supported` proposed JOIN with residual checks;
- confirmed parent-key-in-child collection storage -> `strongly_supported` collection navigation with `row_multiplicity=many`;
- polymorphic collection -> `ambiguity` with concrete targets and required subtype/representation selection;
- insufficient technical evidence -> `unresolved`.

The classification preserves `classification_basis` and does not promote analog SQL to exact observed SQL.
