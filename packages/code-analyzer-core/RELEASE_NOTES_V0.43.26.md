# code-analyzer-core 0.43.26 — Java type structure runtime evidence

Publishes the first complete typed Core evidence artifact: `java-type-structure-evidence/v1`.

The artifact contains repository-relative source units, type declarations, all fields including static fields and record components, inheritance declarations, raw type/field annotations, field/supertype references and enum constants. It includes coverage, explicit diagnostics, provenance and a deterministic content fingerprint. Records are not capped.

It does not interpret JPA, physical mappings, SQL/storage usage, converter mappings, domain entities, effective inherited fields or effective associations.

Publication is transitionally bound to `java_source_observation_build`; semantic routing is still `artifact_kind + schema_version`. Legacy outputs remain available. Runner registration and KLC materialization are separate future iterations.
