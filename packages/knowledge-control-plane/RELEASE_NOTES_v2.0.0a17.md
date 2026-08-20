# analysis-ui 2.0.0a17 — canonical relationship JSON v3

- Frontend Knowledge API types migrated to nested `source`, `target`, `reference` and `join` relationship objects.
- Relationship detail now displays logical identity/version, physical storage key fields, target aliases and encoding status separately.
- Removed frontend dependencies on `target_field`, `join_guidance` and top-level `reference_encoding`.
- Orchestration, publication and same-origin proxy behavior are unchanged.
