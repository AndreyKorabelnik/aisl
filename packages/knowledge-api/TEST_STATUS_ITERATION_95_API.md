# Iteration 95 API test status

## Completed

- `python3 -m compileall -q knowledge_api tests`: passed.
- Focused public SQL/API contract tests: 29 passed.
- Covered:
  - adapter normalization of nested JSON evidence;
  - target-candidate filters and deterministic ranking;
  - attribute insertion request validation;
  - revision-aware GET and POST endpoints;
  - existing SQL relation, source inventory, column context and target-lineage endpoints;
  - canonical OpenAPI equality;
  - CLI and supported runtime layout.
- Real HTTP smoke on the materialized `datamart_profile_fl` Knowledge Layer: passed.
  - first target candidate: `epk_client`;
  - recommended insertion file for `BirthPlace.regionCode`:
    `stg_epk_client_birthplace_snp.sql`.

## Not run

The complete Knowledge API suite and full platform regression were not run. The change is
limited to two read-only endpoints, public models, the generic KLC adapter and OpenAPI.
Publication storage, administration, data-model projections, SQL ingestion, static analysis
and orchestration were not changed. The focused tests exercise the complete affected HTTP path.
