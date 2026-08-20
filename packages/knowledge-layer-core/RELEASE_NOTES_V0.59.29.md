# knowledge-layer-core 0.59.29

System interaction composition over typed boundary evidence.

- Replaces the stale local execution-context dependency on legacy `analysis_record/method_calls.json` with composition from Core `local_call_chain_candidates` already present in `interaction-boundary-evidence/v1`.
- Composes repeated `helper_method_template_and_concrete_call_site` outbound observations into one technical HTTP boundary when helper, client, addressing/path and request/response contract evidence agree.
- Preserves concrete call-site interface IDs, evidence record IDs and scenario operations as provenance/context instead of discarding them.
- Downstream interaction field contracts and cross-repository value-flow consume the composed boundary without special-case logic.

Real four-repository workspace result:
- system interactions: 3 -> 3;
- boundary interactions: 8 -> 3;
- execution contexts: 0 -> 8;
- userinfo contexts: 2/2 Manual Gold;
- update-phone-flags contexts: 1/1;
- update/create contexts: 5/6 (one caller-chain gap remains in Core boundary evidence);
- interaction field contracts: 231 -> 46 by removing six-fold update/create duplication.

No application names, endpoint names or Manual Gold values are hardcoded. Core is unchanged.
