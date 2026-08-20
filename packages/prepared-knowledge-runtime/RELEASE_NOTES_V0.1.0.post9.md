# Prepared Knowledge Runtime 0.1.0.post9

- Adds native read-only `SqlAnalysisEvidenceQuery` for published Core `sql-analysis/v1`.
- Reader receives exact AISL-published manifest/coverage/fact members and never rediscovers producer-local sibling paths.
- Exact SQL item reads preserve source fragments, evidence and coverage after producer workspace deletion or CAS relocation.
