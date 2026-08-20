# Data Model Storage Enrichment — Acceptance

Date: 2026-08-17
Status: PASS

## Real UCP acceptance

Isolated acceptance system: `ucp-data-model-enriched`  
Published revision: `rev-88415df4d14df2ff3827b01c`

Observed execution path:

1. Core `java-type-structure-analyzer` for `ucp-api` and `ucp-tsa-v4`.
2. Core `java-model-storage-analyzer` for `ucp-api` and `ucp-tsa-v4`.
3. KLC `code-declared-data-model`.
4. KLC `model-storage-semantics`.
5. KLC `logical-storage-mapping`.
6. AISL/Knowledge API publication.

The published revision exposes all three derived products required by the rich read path:

- `code-declared-data-model`;
- `model-storage-semantics`;
- `logical-storage-model-mapping` (`logical-storage-mapping`).

For `com.sbt.bm.ucp.retail.model.individual.Individual` the deterministic object-context read returns:

- 52 fields;
- 41 declared relationships;
- `storage_context.status = available`;
- two observed storage identities for `Individual`, preserving their distinct key expressions;
- `birthPlace -> com.sbt.bm.ucp.retail.model.individual.BirthPlace`;
- `birthPlace.storage_semantics.status = ambiguous` because two confirmed exact-target storage observations have different key expressions; neither is silently selected;
- `birthCountry` keeps observed reference-value derivations such as `"Country_" + ...` while its relationship mapping remains `not_observed` when no single published storage relationship mapping is bound;
- physical SQL/PDM mapping remains `not_observed`, `physical_join_confirmed = false`.

There are no object-level gaps hidden by the read tool; ambiguity remains explicit in the relationship storage semantics.

## Non-applicable storage acceptance

A minimal Java repository containing only `example.Customer` was run through the same generic `build-data-model-v1` path.

Observed:

- Core `model-storage-evidence` is published by the producer with `coverage_status = not_applicable` and zero storage observations;
- the requested declared data-model build succeeds and is published;
- the optional storage materializers complete over the explicit not-applicable/empty input without creating storage identities or relationships;
- no guessed storage fact or fallback is present.

This proves that storage enrichment does not make generic data-model generation fail when storage semantics are not applicable.

## Consumer Kit

`data-model/v1` generation for the enriched UCP revision passes and exports five tools, including `get_data_model_object_context`.

## Gold discipline

No Manual Gold was changed or used as a runtime source. This block validates composition and deterministic consumption of existing evidence/knowledge; it does not introduce new semantic Gold claims.
