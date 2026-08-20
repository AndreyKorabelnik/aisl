# Static Analysis Runner 0.9.45

## Knowledge Architecture Audit

Added one generic read-only command and contract:

- `knowledge-architecture-audit`
- `knowledge_architecture_audit/v1`
- `knowledge_architecture_audit_contract/v1`

The audit consumes only official catalogs and evaluates any selected `knowledge_id`. It does not add one command per aspect of knowledge.

The first validated target is `code-declared-data-model`. Current observations exist in Core, while the target path is blocked by:

- missing complete `java-type-structure-evidence/v1` contract;
- missing typed runtime artifact publication;
- missing general Runner typed artifact registration;
- missing KLC `code-declared-data-model` runtime materialization;
- current Task-based common-data-model selection and capability publication.

Runtime repository/workspace execution, KLC and UI are unchanged.
