# Release notes — static-analysis-runner 0.9.46

## Java type-structure evidence registration

Runner now validates and registers the Core-published `java-type-structure-evidence/v1` artifact in repository execution results. Registration is based exclusively on `artifact_kind + schema_version`; Profile and Task values remain request provenance.

Validation covers the Core envelope, kind/schema, prepared-artifact declaration, canonical content fingerprint, artifact ID, analyzer identity, source snapshot, coverage, diagnostics and safe output-relative path. Any inconsistency fails explicitly; no fallback discovery is used.

Suite results preserve the registration inside the task execution and publish a task-local typed-evidence summary. Workspace aggregation remains indirect.

The generic Knowledge Architecture Audit now consumes `core_evidence_contract_catalog/v1`. For `code-declared-data-model`, evidence contract, Core runtime publication and Runner registration gates pass. Remaining blockers are the KLC materialization and removal of legacy Task-semantic routes.

Repository/KLC/UI behavior outside the typed artifact registration path is unchanged.
