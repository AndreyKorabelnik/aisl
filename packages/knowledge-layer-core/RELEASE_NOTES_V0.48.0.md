# knowledge-layer-core 0.48.0

## Evidence-first candidate HTTP transport

- Matched `probable` HTTP boundary interactions now materialize candidate request and
  response wire-to-wire transport edges.
- Candidate edges remain `confidence=probable`; no automatic promotion to confirmed is
  performed.
- Ambiguous and unresolved boundaries remain excluded from the value-flow graph.
- Every HTTP transport edge carries a compact evidence packet:
  - supporting evidence;
  - conflicting evidence;
  - limitations;
  - authority interpretation;
  - contract coverage;
  - candidate or confirmed edge status.
- Loopback and wildcard development authorities are recorded as non-binding environment
  evidence rather than treated as a real service identity.
- The resolver now reports a unique complete path as `confirmed_complete` or
  `probable_complete` and aggregates evidence/limitations across candidate steps.
- Strict traversal remains available through `minimum_confidence=confirmed`.

## Validation

On the frozen multi-repository validation artifact:

- matched probable boundary interactions: 8;
- transport edges before this release: 0;
- candidate transport edges after this release: 226;
- confidence promotions: 0.

Nested DTO reconstruction is intentionally not part of this release.
