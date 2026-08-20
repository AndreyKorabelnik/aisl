# aisl-reporting 0.9.0

## System description redesign

`system-description/v1` now prepares a richer deterministic dataset instead of asking the renderer to infer structure from flat catalogs.

Added:

- profile-owned `audience-policy.yaml` for business, architecture and engineering modes;
- interpreted functional-capability candidates grounded in interfaces and data objects;
- conservative module role hints;
- explicit inbound/outbound system-boundary material and diagram edges;
- representative journeys with exact confirmation boundaries;
- data-domain grouping, full compact storage catalog and separated explicit FK/observed joins;
- compact interface map with evidence IDs and source `path:line` provenance;
- technical appendix and owner-question material;
- legacy capability mapping used only for manual migration acceptance.

The report remains a one-call renderer flow. Preliminary LLM analysis, analysis bundles and `final_response.json` are not restored.

## Validation policy

Markdown validation checks structural headings, evidence citations and unknown evidence IDs. It does not score prose length, table count, diagram count or subjective narrative richness. Reports continue to be saved before validation, with warnings by default and optional strict CI mode.
