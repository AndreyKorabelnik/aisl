# Changed files — code-analyzer-core 0.43.13

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - promotes a custom DAO mutation to a persistent write only when the source implementation proves concrete JOOQ table/column write mappings;
  - preserves overload-aware DAO candidate resolution;
  - resolves direct lambda collection variables back to DAO formal parameters;
  - resolves zero-argument collection accessors to their backing collection before tracing mutators;
  - emits `dao_implementation_not_resolved` only when no concrete cross-DAO mapping was found;
  - publishes a diagnostic count for promoted custom DAO mutations.
- `tests/test_real_app_lineage_patterns.py`
  - adds a full deep-profile regression from Kafka payload through builder/container/custom DAO/JOOQ update to physical columns.
- `pyproject.toml`, `code_analyzer_core/__init__.py`
  - version `0.43.13`.
- release, test and AT900 validation notes for `0.43.13`.
