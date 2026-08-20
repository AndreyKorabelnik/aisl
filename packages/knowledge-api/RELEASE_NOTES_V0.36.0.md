# knowledge-api 0.36.0

Publishes a thin read boundary for Repository Inventory SourceOccurrence knowledge and ID-only Portfolio occurrence references.

- Adds list/get source-occurrence endpoints under repository-inventory.
- Occurrences are read from prepared immutable knowledge only; API never reads industrial source.
- Coverage-gap responses expose explicit localization scope/status.
- Portfolio concept/candidate/gap records propagate occurrence IDs and repository/revision metadata without source paths or bytes.
- No clustering, representative selection, security/export workflow or source interpretation is performed.
- Public OpenAPI is regenerated from the canonical contract builder.
