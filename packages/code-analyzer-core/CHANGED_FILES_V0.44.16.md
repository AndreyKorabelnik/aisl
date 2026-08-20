# Core 0.44.16 changed files

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - validates candidate external source fields against an observed ingress DTO schema before promoting downstream wrapper fields to the external payload;
  - follows deterministic same-class DAO helper delegation with positional parameter binding;
  - composes observed source-object → factory-field → DAO physical-column facts when all identities agree.
- `code_analyzer_core/scanners/java_persistence_jooq.py`
  - recognizes JOOQ `param(...)` placeholders in batch statements.
- `tests/test_real_app_lineage_patterns.py`
  - regression coverage for payload-field guard, JOOQ helper delegation, enhanced-for batch mappings and factory→physical composition.
- version/release/test metadata updated to `0.44.16`.
