# knowledge-layer-core 0.49.0

## Evidence-backed nested HTTP wire reconstruction

- Nested outbound request paths already observed as exact operation-scoped boundary occurrences
  are published even when the compact source interface contract is shallow.
- Strict collection-member reconstruction supports `stream().map(methodReference)` followed by
  nested builder composition.
- When the dedicated method-reference artifact is absent, an exact fallback derives the binding
  from a unique same-class helper referenced in a local initializer, with one helper parameter and
  one observed return type.
- Reconstruction no longer requires an ingress/execution context. In its absence, a direct
  repository-local field-flow path to the outbound boundary is mandatory.
- Reconstructed field contracts, synthetic source wire nodes, serialization edges and HTTP
  transport edges remain `confidence=probable` and retain complete reconstruction provenance.
- Existing exact top-level contracts and confirmed/probable boundary semantics are unchanged.

## Real validation

For `POST /updatePhoneFlags` on the frozen real multi-repository validation set:

- transport wire paths increased from 2 to 7;
- five new nested paths were reconstructed;
- all five manually proven attribute mappings reached target controller parameters as
  `probable_complete` paths;
- the conditional `changeDt -> endDate` path retained its `BooleanUtils.isFalse(flagDto.value)`
  guard;
- confidence promotions remained zero.
