# knowledge-layer-core 0.59.31

Composed outbound boundary wire-node propagation for cross-repository value flow.

- Exposes KLC-composed HTTP outbound boundaries to the value-flow materializer as first-class interface identities.
- Materializes source wire nodes against the composed boundary ID instead of requiring a matching raw Core call-site interface ID.
- Reuses typed interaction field contracts for the composed source interface, preserving field-contract provenance.
- Does not alias a composed boundary to an arbitrary member observation and does not add application-specific rules.
- Core evidence contracts and confidence/matching policy are unchanged.

Real four-repository validation:
- field contracts: 46;
- cross-repository transport edges: 46 (previously 9);
- userinfo: 2/2;
- phone flags: 7/7;
- update/create: 37/37.

Known separate gap: the real `name.surname` composed source wire node has no observed source-local incoming value-flow edge, so a source-local surname journey cannot yet be claimed from this fix alone.
