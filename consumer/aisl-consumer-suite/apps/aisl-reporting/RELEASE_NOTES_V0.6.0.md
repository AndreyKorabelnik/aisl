# aisl-reporting 0.6.0

## Added

- `git-change-impact-report/v1` over deterministic `code-analyzer-core` git-change artifacts.
- Complete changed-file, hunk, schema, lineage, transformation, flow and event delta dataset sections.
- Neutral author/committer/reviewer traceability metadata without raw email addresses.
- Deterministic complexity, data-impact, risk, quality-evidence and confidence classifications.
- Profile-specific migration expectations preserving 29 old-profile capabilities.

## Changed

- `ReportRequest` is now `report_request/v2`.
- Replaced the Knowledge-Layer-specific `knowledge_layer` field with canonical `input_kind` and `input_artifact`.
- All existing profiles explicitly use `input_kind=knowledge_layer`.
- CLI options are now `--input-artifact` and `--input-kind`.

## Removed

- The assumption that every report input is a DuckDB Knowledge Layer.
- Any need for the old `git-change-complexity-assessment -> final_response.json -> business-report` LLM chain.

## Validation

- Reporting suite with real UCP and git-change fixtures: 12 passed, 4 fixture-dependent skips.
- New git-change dataset: 28,377 canonical bytes, 21 evidence refs.
- Generated report: 9 required headings, 11 exact evidence citations, 0 unknown IDs.
- Migration gate: 29/29 capabilities passed, status `accepted_with_known_differences` because no historical report artifact was available for textual A/B.
