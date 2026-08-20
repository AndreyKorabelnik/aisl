# knowledge-layer-core 0.31.1

Iteration 31.2 composes exact local mapper evidence into workspace request lineage.

- imports `attribute_derivations.json` as a flow-lineage query artifact;
- requires signature-aware caller/callee bindings and exact DTO type agreement;
- maps mapper builder targets to outbound wire fields through the observed request contract;
- rejects ambiguous overloads, arbitrary expressions, leaf-name matching and candidates outside the operation corridor;
- preserves existing strict `end_to_end_observed` paths and adds `local_derivation_composed` only when all evidence segments are present.

Real four-system replay: 24 existing strict rows + 24 exact composed rows, all 24 additions present in the manual baseline, 0 extra rows.
