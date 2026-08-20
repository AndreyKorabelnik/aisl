# Knowledge API 0.23.0

- Adds one thin revision-bound `system-description/query` endpoint over the existing KLC `ReportingQueryService` facade.
- Supports scope overview, repository composition, declared technologies, interfaces, integrations, events, observed storage targets, coverage, gaps and representative journeys.
- Selects only a prepared `system-description` artifact that publishes `common.system-description`; missing knowledge remains an explicit `knowledge_artifact_unavailable` response and is never reconstructed from other artifacts.
- Query-specific filter validation stays explicit; no business-purpose inference, runtime-topology inference, storage relationship inference or scenario reasoning was added to Knowledge API.
