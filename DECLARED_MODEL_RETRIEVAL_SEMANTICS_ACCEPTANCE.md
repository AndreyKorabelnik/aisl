# Declared-model retrieval / semantic-discipline acceptance

Date: 2026-08-15

## Tests actually run

- Knowledge API declared-model + public contract tests: 18/18 PASS.
- knowledge-integration package tests: 12/12 PASS.
- knowledge-assistant package tests: 84/84 PASS.
- knowledge-chat backend tests: 5/5 PASS; one pre-existing FastAPI duplicate Operation ID warning remains.
- `find_attributes.py` semantic-policy/candidate-hint synthetic smoke: PASS.
- compile/import/version smoke for changed runtime modules: PASS.

## Representative acceptance cases

- Field documentation match is surfaced without returning the full object field set.
- Exact type lexical result is deterministically ranked ahead of weaker field/type substring results.
- Incoming declared binding is visible for a bound dictionary/type candidate.
- Standalone unbound type reports `has_observed_incoming_binding=false`.
- Generic container storage capacity cannot remain a positive semantic match.
- Related-but-different concept cannot remain a positive semantic match.
- Unbound type without observed binding is demoted from a unique strong match to ambiguity.
- Partial component coverage cannot remain `confirmed`.
- Projected-search zero-novelty stopping does not prevent one explicit all-declared scope expansion.

## Test correction

`test_contract_v1.py` had a stale `EXPECTED_PATHS` set that omitted the already-active `/llm-integration-profile` endpoint. Runtime and generated OpenAPI already contained that endpoint. Only the stale test expectation was corrected; no endpoint was added by this block.

## Regression scope

Full framework regression was not run. Changes are confined to the declared-model read boundary and consumer-side semantic policy; Core, Runner, KLC and KCP are unchanged.
