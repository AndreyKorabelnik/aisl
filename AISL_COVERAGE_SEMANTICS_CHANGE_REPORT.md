# AISL KnowledgeProduct coverage semantics — change report

Date: 2026-08-15
Status: COMPLETE

## Scope

This block makes published KnowledgeProduct coverage explicit for the three representative data-model products used by the real AISL UCP/PDM acceptance. It does not add a parser, analyzer, second materializer, API inference path, or compatibility adapter.

## Changed owner

`knowledge-layer-core 0.61.0a29` remains the owner of KnowledgeProduct materialization metadata.

### code-declared-data-model

Product-level coverage is now a lossless aggregation of existing Core repository coverage plus KLC model gaps:

- `analysis_status`;
- repository counts/statuses;
- Java files in scope/parsed/failed/with parse errors;
- unresolved/ambiguous type-reference counts;
- unsupported declaration count;
- model gap count;
- exact per-repository source coverage.

No source fact is guessed or re-derived from source code in KLC.

### physical-data-model

Product-level coverage now exposes the existing physical-model parser contract and materialized counts:

- `analysis_status`;
- `coverage_basis=physical_model_parser_contract`;
- table/column/key/relationship counts;
- gap count;
- `does_not_claim_business_semantic_completeness=true`.

### logical-physical-model-mapping

The ambiguous old form `coverage.status=complete` for a zero-mapping run is removed. Coverage dimensions are now separate:

- `analysis_status` — whether the supported mapping analysis completed without recorded mapping gaps;
- `mapping_coverage_status` — outcome over observed explicit persistence-mapping evidence;
- observed/applicable/matched/unresolved/ambiguous/not-applicable counts;
- explicit non-claims that all logical or physical objects are mapped.

With zero observed persistence mappings, the correct status is `mapping_coverage_status=no_mapping_evidence`, not semantic `complete`.

## Architecture decision

See AISL ADR-009: Coverage statuses are dimension-specific. Analysis completion is not semantic completeness.

## Tests

- full KLC suite: 247 passed, 8 skipped;
- real UCP + PDM production: PASS;
- official Knowledge API publication into a clean catalog: PASS;
- published coverage payload parity: PASS;
- consumer-only universal exact read: PASS.
