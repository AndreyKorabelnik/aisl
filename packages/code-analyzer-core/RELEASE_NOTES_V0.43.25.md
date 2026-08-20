# code-analyzer-core 0.43.25 — Core Evidence Contract Catalog

Introduces one extensible Core-owned catalog for typed evidence contracts. The first contract is `java-type-structure-evidence/v1`, used by the future KLC `code-declared-data-model` materialization.

The contract publishes complete raw Java declarations without persistence, physical, SQL, storage, converter/builder or effective-model interpretation. It explicitly retains fieldless types and static fields and has no record cap.

No analysis runtime changed. `java-type-structure-evidence/v1` is defined but not emitted in this release.
