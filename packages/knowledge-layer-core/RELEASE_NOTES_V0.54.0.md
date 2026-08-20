# knowledge-layer-core 0.54.0 — code-declared data-model runtime

- implements the first complete typed Core → Runner → KLC knowledge path;
- accepts only Runner-registered `java-type-structure-evidence/v1`;
- validates semantic identity, artifact fingerprint, artifact ID, SHA-256, source snapshot and safe relative location;
- materializes code-declared source units, types, fields, inheritance, type references, annotations and enum constants;
- derives effective inherited non-static fields inside KLC;
- materializes resolved field-type references without claiming business-association semantics;
- publishes explicit diagnostics and KLC derivation gaps;
- supports repository and workspace scopes;
- does not read or fall back to `code_conceptual_model/v2`;
- removes the active `suite.common-data-model-selection` Task route from the materialization catalog;
- UI, Knowledge API, Reporting and Assistant are unchanged.
