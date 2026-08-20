# AISL Published Persistence Pilot — Change Report

Date: 2026-08-16  
Status: **COMPLETE**

## Architectural change

AISL now has an executable pilot of canonical persistence ownership for published immutable KnowledgeProducts.

Semantic ownership did not move:

- Core still owns observed evidence semantics and analyzers;
- KLC still owns derivation/materialization semantics;
- Runner/KCP still own execution lifecycle.

The new responsibility begins only at successful publication.

## Knowledge API 0.31.0

Added filesystem `AislArtifactStore` and publication import/finalize of published bytes into an AISL-owned content-addressed namespace.

Publication now supports:

- existing KLC derived KnowledgeProducts;
- one explicit observed pilot product: `java-type-structure-evidence/v1`;
- `origin_kind=observed|derived`;
- generic `product_slot_id` for COW replacement;
- producer / producer-contract provenance;
- exact same-revision product dependencies;
- structural rejection of stale exact dependencies.

Existing SQLite catalog representation is retained. No second product registry and no schema-normalization project was introduced.

All KLC derived database/manifest bytes are also imported into AISL storage during publication, so consumer autonomy is not limited to the observed pilot product.

## Prepared Knowledge Runtime 0.1.0.post8

Added native exact read support for `java-type-structure-evidence/v1`.

Added explicit database opening with separately supplied published manifest metadata. This removes assumptions that a DuckDB artifact must retain a `.duckdb` filename or a producer-side sibling manifest.

## AISL Contract 0.3.0b5

Formalized:

- observed vs derived KnowledgeProduct origin;
- semantic producer provenance;
- multi-owner registry projection rather than a second catalog;
- physical locator independence from product identity;
- exact product dependency integrity inside a KnowledgeRevision.

## Intentionally unchanged

- Core analyzers/evidence semantics;
- Runner execution-result schema (`knowledge_execution_result/v2` already carries evidence + knowledge artifacts);
- KLC materializers/derived semantics;
- KCP job state;
- Knowledge Integration profile/tool catalog;
- SQLite catalog normalization;
- multi-file Core artifact publication;
- GC.

## Physical publication semantics

Producer artifact → validate → import into AISL Artifact Store → verify content → atomic blob finalize → catalog publication.

The pilot backend uses local filesystem CAS. Backend optimization is not part of the semantic contract; hardlink is not assumed.

## Real acceptance

See `AISL_PUBLISHED_PERSISTENCE_PILOT_ACCEPTANCE.md` and the recovery `REAL_E2E_ACCEPTANCE.json` / `REAL_COW_ACCEPTANCE.json`.
