# Real Multi-Product AISL Acceptance — UCP + PDM

Date: 2026-08-15
Status: PASS for Producer → Publication → consumer-only AISL read boundary; KCP one-shot lifecycle is separately unresolved in this container.

## Inputs

Formalized real inputs:

- UCP `ucp-api` Java sources;
- UCP `ucp-tsa-v4` Java sources;
- real B2C PowerDesigner PDM `CDO_B2C_PDM - ag 20260710.pdm`.

No Gold or LLM inference was used to construct the published KnowledgeProducts.

## Production

Canonical Runner `0.10.25` executed the existing `build-effective-data-model-v1` plan with KLC `0.61.0a29`.

Observed produced products:

1. `code-declared-data-model` — 1326 declared types, 6045 declared fields, 7165 effective fields, 1573 relationships, 31 model gaps.
2. `physical-data-model` — 522 tables, 11940 columns, 498 keys, 370 relationships, 0 physical-model gaps.
3. `logical-physical-model-mapping` — 0 observed mapping records, 0 mapping gaps.
4. `effective-data-model`.
5. `model-domain-cluster-view`.

`knowledge_execution_result/v2` projected successfully into the AISL Producer Contract: 5 products, 8 construction dependency edges, 0 contract issues.

## Coverage semantics validated on real data

### Code-declared product

Published product coverage preserves observed Core coverage rather than `{}`:

- `analysis_status=partial`;
- `repository_count=2`;
- repository statuses: one complete, one partial;
- 1061 Java files in scope and parsed;
- 14 unresolved type references;
- 17 unsupported declarations;
- 31 model gaps.

### Physical product

Published product coverage is an analysis-contract projection, not a claim that the PDM is business-semantically complete:

- `analysis_status=complete`;
- `coverage_basis=physical_model_parser_contract`;
- 522 tables / 11940 columns / 498 keys / 370 relationships;
- `gap_count=0`;
- `does_not_claim_business_semantic_completeness=true`.

### Logical/physical mapping

The previous ambiguous `coverage.status=complete` for zero mappings was removed. The real product now publishes:

- `analysis_status=complete` — the supported mapping analysis executed without recorded mapping gaps;
- `mapping_coverage_status=no_mapping_evidence`;
- `observed_mapping_count=0`;
- `matched_mapping_count=0`;
- `mapping_coverage_basis=observed_explicit_persistence_mapping_records_only`;
- explicit flags that the product does not claim all logical or physical objects are mapped.

This is the intended AISL rule: completion of an analysis contract is not the same dimension as semantic mapping completeness.

## Publication

The completed execution result was published through the official Knowledge API publication service into a clean catalog.

Published system: `aisl-real-ucp-pdm`  
Published revision: `rev-97726fa47b2de005da068bd1`  
KnowledgeProducts: 5  
Published capabilities: 17

The publication catalog preserved the coverage payloads above unchanged.

## Consumer-only read

After production completed, only the AISL serving/read side was needed.

### Code exact read

`KnowledgeItemRef` for `serviceStartDate`:

- product: `code-declared-data-model`;
- local item: `code_declared_field_f33a2567e4ff2ee79b28`;
- observed field: `AbstractParty.serviceStartDate`;
- documentation: `Дата начало обслуживания клиента`;
- source fragment: `ucp-models/ucp-common-model/src/main/java/com/sbt/bm/ucp/common/model/party/AbstractParty.java:160-162`;
- evidence state: `available`.

### Physical exact read

A real PDM table was read through the same universal item boundary and returned exact PDM object evidence.

### Agent SDK

`knowledge-integration` `get_knowledge_item` produced a revision-pinned request for the real published revision and returned the same exact code-field evidence. No Core, Runner or KLC was needed for this read.

## Production scope versus publication target

Current framework portfolio tests prove that execution scope and publication target are intentionally distinct concepts: repository-scoped inventory products may be published under one system-level AISL scope. This validates ADR-010 and is why `PublicationCandidate` carries `production_scope`, not a claimed target KnowledgeScope.

## Limitations / unresolved

- Real positive logical↔physical correspondence was not available for these inputs: the product observed zero explicit persistence mapping records. AISL correctly reports `no_mapping_evidence`; it does not synthesize correspondence.
- Item-level Coverage remains `not_available` unless the typed product publishes an official item-level coverage fact. Product-level coverage must not be silently reused as item-level coverage.
- Universal exact item projections remain intentionally bounded to the currently implemented typed product families.
- The KCP one-shot real run in this container did not advance its job lifecycle after the Runner subprocess had already completed. The same immutable execution plan completed through the canonical Runner directly, and official Knowledge API publication/read passed. Therefore KCP one-shot end-to-end is **not claimed PASS** and is a separate operational investigation.
