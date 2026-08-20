# Change report — UCP 91 AISL reachability block

Date: 2026-08-15

## Runtime changes

**None.** No framework package source, runtime contract, producer, materializer or API implementation was modified.

## Why no runtime change was made

The current prepared AISL knowledge contains all 29 non-ambiguous positive Manual Gold object/field facts. Current deterministic read mechanisms can reach all of them using bounded lexical search, explicit scope expansion, exact detail and/or root-type navigation. No generic missing evidence/read projection was demonstrated.

Changing Core/KLC/API to improve a contaminated benchmark score would violate the architecture and Gold discipline.

## Added validation assets

- `UCP_91_AISL_REACHABILITY_ACCEPTANCE.md`;
- `validation/ucp-91-aisl-reachability-2026-08-15/POSITIVE_REACHABILITY_29.json`;
- `.../POSITIVE_REACHABILITY_FOLLOWUP_6.json`;
- `.../SEMANTIC_GUARD_ACCEPTANCE.json`;
- `.../NONBLIND_RETRIEVAL_DIAGNOSTIC.md`;
- clean `blind-consumer-pack/` with 91 inputs, policy, result schema and post-freeze evaluator;
- synthetic evaluator test output.

## Versioning

All package versions remain unchanged because no package code changed.
