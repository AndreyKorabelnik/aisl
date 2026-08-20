# AISL Reference Data / NSI — change report

Date: 2026-08-16  
Status: **REFERENCE_DATA_AISL_BLOCK_COMPLETE**

## Changed modules

### Knowledge API 0.30.16

Added a compact facts-only Reference Data projection over the already published `reference-data/v1` KnowledgeProduct.

Changes:

- added response model `ReferenceDataGuidanceResponse`;
- added schema `reference-data-guidance/v1`;
- added `GET /api/knowledge/v1/systems/{system_id}/reference-data/guidance`;
- optional token supports both compact discovery and exact candidate context;
- exact KLC-owned summary counts are retained while presented rows are bounded;
- representative usage observations are selected deterministically by observed kind before filling the remaining presentation limit;
- unfiltered discovery cards intentionally omit heavy sample/evidence detail that is available in token-specific drill-down;
- added explicit `projection.semantic_derivation = none` and classification-boundary metadata;
- existing detailed `POST /reference-data/query` remains unchanged and available for drill-down;
- regenerated canonical OpenAPI snapshot and public-route contract.

The API does not assign reference semantics, definition authority or own-NSI status.

### Knowledge Integration 0.1.15

- Reference Data Integration Profile advanced to profile v2;
- tool catalog contract advanced to v8;
- added capability-gated `get_reference_data_context`;
- tool uses the new guidance endpoint and remains pinned to `scope.revision_id`;
- common Reference Data workflow now starts with the compact context;
- `get_reference_data_landscape`, search and candidate-context tools remain detailed drill-down surfaces;
- retrieval policy explicitly says that local definition evidence is not proof of official NSI ownership/global authority.

## Unchanged producer/runtime owners

No runtime code changed in:

- evidence-common 0.23.2;
- code-analyzer-core 0.44.23a5;
- static-analysis-runner 0.10.25;
- prepared-knowledge-runtime 0.1.0.post7;
- knowledge-layer-core 0.61.0a32;
- knowledge-reporting 0.18.0;
- knowledge-control-plane 1.2.0a23;
- aisl-contract 0.3.0b4.

No new analyzer, second Reference Data producer, alternative materializer, compatibility adapter or Gold-driven runtime branch was introduced.

## Tests added / changed

Knowledge API contracts cover:

- compact Reference Data guidance;
- no automatic own-NSI/reference-semantics assignment;
- enum/control/value-set non-promotion;
- public route/OpenAPI parity.

Knowledge Integration contracts cover:

- profile v2;
- compact tool binding and fixed bounds;
- one pinned revision;
- detailed tools retained for drill-down.

## Real acceptance

Authoritative real publication:

- job `job-2d8e2dd6fada45668205498e59ac5005`;
- revision `rev-7e8a9ec88020277028ac41cb`;
- 25/25 technical semantic-definition checks;
- 25/25 policy guards;
- 22/22 frozen semantic cases represented;
- compact real reads preserve the `operatorId` external-ingress versus `MOBILEOPERATOR` local-definition distinction.
