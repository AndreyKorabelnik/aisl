# knowledge-api 0.37.1 — test status

Date: 2026-08-17

## Targeted observed/AISL persistence regression

- 10/10 PASS
- Covers multi-repository same-kind observed publication.
- Covers source-scoped incremental COW replacement.
- Covers duplicate same-source+kind rejection.
- Covers observed+derived persistence, SQL multifile persistence, partial/failed observed status and artifact-store relocation.

## Contract/OpenAPI

- 2/2 PASS (`test_exported_contract_openapi_matches_generated_document`, runtime-backed routes smoke).

## Real UCP acceptance

Scenario: `build-data-model-v1`

Sources:
- `ucp-api`
- `ucp-tsa-v4`

Result:
- Runner: completed
- `code-declared-data-model`: completed
- Knowledge API publication: PASS
- Published revision: `rev-cf1820d42ff0cf021ccb358a`
- Observed slots:
  - `core:ucp-api:java-type-structure-evidence`
  - `core:ucp-tsa-v4:java-type-structure-evidence`
- Derived slot:
  - `klc:code-declared-data-model`

No full framework regression was run for this isolated Knowledge API publication fix; Core/Runner/KLC code is unchanged.
