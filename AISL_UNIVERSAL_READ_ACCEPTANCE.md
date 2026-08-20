# AISL Universal Read — Acceptance

Date: 2026-08-15

## Functional acceptance

- exact code-declared field read with source evidence: PASS;
- exact physical table read without invented correspondence: PASS;
- exact logical/physical entity mapping with `maps_to` endpoints from published product identities: PASS;
- unsupported item kind is explicit `unsupported`, not empty/absence: PASS;
- official OpenAPI includes the universal route: PASS.

## Test results

- prepared-knowledge-runtime full suite: **4/4 PASS**;
- knowledge-api full suite: **90/90 PASS**;
- focused contract/read/publication regression: **36/36 PASS**.

## Limitations

- universal reverse correspondence lookup from arbitrary source/target items: not implemented;
- universal item-level Coverage: not synthesized; currently `not_available` unless a typed fact exists;
- representative projections are limited to code-declared, physical model and logical/physical mapping products;
- real published multi-product revision end-to-end validation: NOT RUN (artifact unavailable in current recovery set).
