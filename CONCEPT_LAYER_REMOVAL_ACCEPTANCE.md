# Concept Layer Removal — Real Acceptance

Date: 2026-08-17
Status: PASS

Fresh forced-rebuild publications were completed for:
- Java-heavy UCP repository (`concept-cleanup-ucp`);
- SQL/YAML datamart (`concept-cleanup-datamart`).

Verified on both published Repository Inventory v5 products:
- zero concept tables;
- no concept report/status/classification payload;
- no repository-local `structural_novelty` output;
- `unknown_primitive` only with explicit outside-analyzer-frontier basis;
- `structural_salience_score` is rank metadata;
- structural family observed dimensions are exact-parity with the previous Source Localization canonical;
- repository file path/extension/SHA are exact-parity;
- SourceOccurrence remains functional (Java exact span, YAML file-level provenance);
- old `/repository-inventory/concepts` endpoint returns 404;
- OpenAPI has no concept route;
- Portfolio has no concept facet or concept payload.

Observed real counts:
- UCP: 6 structural families = 4 `none` + 2 `unknown_primitive`; 670 source occurrences; 678 occurrence links.
- Datamart: 28 structural families = 22 `none` + 6 `unknown_primitive`; 491 source occurrences; 868 occurrence links.

Machine record: `validation/concept-layer-removal-2026-08-17/REAL_CONCEPT_LAYER_REMOVAL_ACCEPTANCE.json`.
