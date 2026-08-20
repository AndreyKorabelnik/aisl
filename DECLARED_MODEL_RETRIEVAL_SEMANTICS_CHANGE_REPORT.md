# Declared-model retrieval and semantic-discipline change report

Date: 2026-08-15
Status: IMPLEMENTATION_COMPLETE_PENDING_REAL_91_ATTRIBUTE_RERUN

## Evidence basis

This block was derived from:
- the 91-attribute Manual Gold built from the supplied UCP source archives;
- the structural diff between that Manual Gold and the last observed framework result;
- the latest Assistant traces showing retrieval misses, budget gaps and semantic overclaim patterns.

Observed baseline findings included missed prepared facts (`serviceStartDate`, `creditHistory`, `pastDueEvents`, `investorRiskProfileScore`), unbound type/dictionary overclaim, generic-container overclaim, and unstable lexical candidate ordering.

## Architecture decision

No Core analyzer and no KLC materializer was added or changed. The required observed facts already exist in prepared `code-declared-data-model/v1` tables: types, effective/inherited fields, documentation and declared relationships.

The fix is a single read/consumption path:

Prepared code-declared knowledge -> prepared-knowledge-runtime ranked read -> Knowledge API -> knowledge-integration compact view -> Knowledge Assistant semantic policy.

## Changes

### prepared-knowledge-runtime 0.1.0.post5
- Query contract bumped to `code-declared-data-model-query/v2`; prepared artifact schema remains `code-declared-data-model/v1`.
- `list_code_declared_objects` now ranks lexical candidates deterministically instead of FQCN-only ordering.
- Search returns bounded `match_evidence` for the observed type/field fact that caused the hit.
- Search/detail return `binding_summary` with observed incoming/outgoing declared relationship counts and bounded incoming examples.
- `filters.search_scope` is explicit: `type_annotation_projection` or `all_declared_types`.
- Retrieval scores are retrieval metadata only; no business confidence is inferred.

### knowledge-api 0.30.7
- Public declared-object models expose retrieval score/basis, bounded match evidence and binding summary.
- OpenAPI regenerated.
- Package pins the matching prepared runtime and knowledge-integration versions for this read contract.

### knowledge-integration 0.1.7
- Compact discovery cards retain bounded match evidence and binding summary without reintroducing full field dumps.
- Batch search merge keeps the strongest lexical card, merges query provenance/match evidence and deterministically reranks unique candidates.
- Data-model policy requires explicit projected -> all-declared scope expansion when projected evidence is insufficient.
- Profile explicitly states that lexical retrieval score is not semantic confidence.

### knowledge-assistant 0.25.1.post16
- Added deterministic data-model semantic evidence policy.
- Positive semantic results must classify `evidence_role`, `semantic_relation`, binding status and match scope; missing classification becomes an explicit gap.
- `generic_container` / `storage_capability_only` and `related_concept` / `related_but_different` cannot support positive matches.
- An `unbound_type` with `no_observed_binding` cannot remain a unique strong positive match.
- Partial composite coverage cannot remain `confirmed`.
- Search stopping is scope-aware so explicit all-declared expansion is not silently blocked by prior zero-novelty searches in a narrower projection.

### standalone attribute workflow
- `find_attributes.py` emits/validates evidence roles and composite coverage.
- Prior positive results may be reused only as non-evidence candidate hints; every reuse must be reverified through tools.
- Runtime gap/coverage rules remain authoritative over model wording.

## Explicit non-changes

- No code-analyzer-core change.
- No knowledge-layer-core change.
- No Runner/KCP change.
- No prepared revision rebuild required.
- No embeddings/vector index added.
- No UCP-specific runtime hardcoding.

## Limitations / unresolved

- The final combined code has not yet been rerun on all 91 attributes because the user cannot run it at this moment.
- Therefore improvement in Manual-Gold precision/recall and total latency is NOT YET OBSERVED.
- Semantic relation (`exact`, `partial`, `related_but_different`, etc.) is still an LLM interpretation over observed evidence; the runtime constrains unsupported confidence but does not claim strict semantic proof.
- If deterministic ranked lexical retrieval still misses semantically distant phrases after the real rerun, a reusable prepared lexical/semantic retrieval index can be considered separately. It is not implemented in this block.
