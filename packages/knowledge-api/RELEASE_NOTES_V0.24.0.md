# knowledge-api 0.24.0

- Adds a thin revision-bound `declared-summary` endpoint over the canonical KLC code-declared model query service.
- Extends declared-object responses with observed annotations, inheritance/cardinality metadata and provenance already owned by KLC.
- Supports exact annotation filters without API-owned semantic classification or fallback to effective/physical models.
- Keeps repository/workspace scope pinned to one prepared revision.
