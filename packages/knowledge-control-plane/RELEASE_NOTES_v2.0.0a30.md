# Analysis UI 2.0.0a30

Adds a Knowledge-Layer-only full-pipeline mode for prepared assistant contexts.
When `parameters.build_report` is `false`, static analysis and Knowledge Layer
materialization run normally, the report stage is explicitly marked `skipped`, and the
immutable system revision is published without an LLM report. Existing full-pipeline
behavior remains unchanged by default.

The parameter is excluded from static-analysis cache identity, so a later ordinary run can
reuse the same analysis and Knowledge Layer and build a report separately.
