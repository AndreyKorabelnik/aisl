# knowledge-layer-core 0.33.0

## Iteration 31.4 R1 — exact response attribute lineage

- Materializes response-direction field lineage for matched system operations.
- Composes downstream HTTP response boundary fields through observed local field-flow into exact source-system response contract fields.
- Uses confirmed operation-specific builder derivations as a conservative fallback when a local getter edge is missing.
- Resolves duplicate response builder fields within the exact derivation operation; no global field-name guess is made.
- Preserves request lineage and interaction graph counts.
- Leaves empty external DTO response contracts and whole-object passthroughs unresolved.
- Uses no fuzzy, semantic or approximate field-name matching.

Validated on the four-system workspace:

- systems / system interactions / operation interactions: 4 / 3 / 9;
- request field contracts: 231;
- request attribute lineage: 58;
- response attribute lineage: 29;
- total attribute lineage: 87;
- manual response baseline covered: 15 / 21;
- additional exact observed response fields: 14;
- remaining manual cases: 6.
