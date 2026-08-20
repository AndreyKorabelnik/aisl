# UCP 91 — AISL reachability acceptance

Date: 2026-08-15  
Status: **PASS — AISL/read reachability; external-agent blind score still unresolved**

## Purpose

Determine whether the historical 91-attribute misses are caused by missing prepared AISL knowledge/read projections or by consumer retrieval/reasoning. This is not a mathematical proof and it is not a blind LLM benchmark. It is a Gold-driven acceptance over already-produced deterministic knowledge.

## Canonical consumer input

Prepared UCP code-declared knowledge from the current production path:

- repository: `ucp-api`;
- Java files parsed: 592;
- declared types: 828;
- declared fields: 4,872;
- effective fields: 6,767;
- relationships: 1,491;
- explicit model gaps: 24;
- analysis remains `partial` because unresolved type references and unsupported declarations remain visible.

No Core/Runner re-analysis was triggered for the attribute questions.

## Historical checkpoint

The prior full 91 external-agent result, before the current retrieval blocks were rerun, accepted 12 of 29 non-ambiguous Gold-positive attributes (41.4% positive recall) and 12 of 26 positive outputs (46.2% positive precision). Those are agent-result metrics, not AISL reachability metrics.

## Observed reachability result

Manual Gold contains 29 non-ambiguous positive target facts (`confirmed`, `strongly_supported`, or `probable`). Acceptance checked their exact object/field identities against current prepared knowledge.

Observed:

- exact Gold-positive facts present in prepared knowledge: **29/29**;
- exact target field surfaced in top-5 by the frozen bounded lexical diagnostic query plan: **23/29**;
- of those 23, projected model search alone surfaced 15;
- 8 required explicit `all_declared_types` expansion;
- the remaining 6 were all reachable by one bounded follow-up/navigation step: **6/6**;
- final Gold-driven exact read reachability: **29/29**.

Representative follow-ups:

- `адреса` → `AbstractParty.addresses`, rank 1;
- `предпочитаемые языки коммуникации` → `CustomerJourney.preferredLanguages`, rank 1;
- `активного продукта` → `ProductInfo.hasActiveProduct`, rank 1;
- `связь клиента с группами` → `AbstractParty.partyToPartyGroups`, rank 1;
- `facts` → `OmniMemoryIndividualFacts.facts`, rank 1;
- `Individual` is one of 18 observed `MetaRootEntity` roots; exact detail contains inherited `id`, while the root annotation itself declares `id="id"` and `collocationId="id"`.

The follow-up queries are Gold-driven acceptance probes and therefore are **not** a new external-agent score. In particular, `события → facts` requires semantic/translation reasoning owned by the consumer.

## Semantic-confidence acceptance

The current read contract exposes enough evidence to avoid several representative historical overclaims:

1. Client segment: `Segment` exists, but its candidate has no observed incoming client binding → `unbound_type`, not a confirmed client segment.
2. Closed-product reason: `PartyAgreementEndReason` is semantically named but has no observed binding to a client product/agreement → ambiguity remains.
3. Preferred communication channel: observed `Consent.consentChannels` and `InfoFlowChannel` express consent/source channels, not preference → `related_concept`.
4. Financial literacy: `Individual.literacy` is explicitly documented as `Неграмотность`, not financial-literacy level → `related_concept`, not a positive semantic match.
5. Active restrictions: change-control `LockInfo`/`TwoManRuleEntity` and real-estate restrictions are contextual locks/restrictions, not generic client/product compliance blocks → context must be preserved.

The existing generic consumer policy already requires the agent to distinguish `direct_field`, `bound_type`, `unbound_type`, `partial_component`, `related_concept`, `generic_container`, and `no_candidate`, and to preserve ambiguity/unresolved results.

## Architectural conclusion

**No new AISL producer/read defect was demonstrated by this block.** Therefore Core, Runner, KLC, Prepared Runtime, Knowledge API and Knowledge Integration runtime code were intentionally left unchanged.

Strongly supported conclusion: the historical 41.4% positive recall was far below the knowledge/read ceiling. The remaining quality risk is now primarily consumer-owned candidate discovery, translation/synonym choice, exact-detail inspection, ranking/semantic verification, and confidence discipline.

This does not claim that the external agent will achieve 29/29. A truly blind rerun is still required.

## Clean blind rerun package

`validation/ucp-91-aisl-reachability-2026-08-15/blind-consumer-pack/` contains only:

- the 91 input attribute names;
- output schema;
- current generic consumer policy;
- isolation/freeze protocol;
- post-freeze structural evaluator.

It intentionally contains no Manual Gold answers and no Gold target FQCN/field map. The evaluator accepts Gold only as an explicit argument after the agent output SHA-256 has been frozen.

## Tests / checks performed

- prepared knowledge exact target existence: **29/29 PASS**;
- frozen bounded retrieval diagnostic: **23/29 exact target fields in top-5**;
- bounded follow-up/navigation for remaining targets: **6/6 PASS**;
- representative semantic-guard evidence capture: **5 cases PASS as evidence availability checks**;
- blind input isolation: **91/91 records contain only `input_index` and `attribute`**;
- evaluator synthetic structural test: **PASS**;
- evaluator Python compile: **PASS**.

No framework package code changed, so package full regressions were not rerun in this validation-only block. The latest completed package regressions remain the prior canonical acceptance results.

## Remaining gap / next acceptance

Run the clean 91 inputs through an external agent against a pinned current AISL revision, freeze the result SHA-256, then compare with Manual Gold. Classify every discrepancy as:

- AISL knowledge gap;
- AISL read/projection gap;
- agent discovery/retrieval gap;
- agent semantic/ranking/confidence error;
- ambiguity/unsupported scenario;
- Gold semantic difference/error.

Only a demonstrated AISL gap should trigger another producer/read change.
