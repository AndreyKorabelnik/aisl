# Analysis UI 2.0.0a32

Adds repository-based preparation to the existing source-and-datamart context wizard.
The wizard registers source and datamart repositories, creates separate workspaces, selects
static profiles by their declared `analysis_purposes`, and starts two existing orchestration
jobs in knowledge-only mode.

The built-in `knowledge-context-pipeline:v1` performs static analysis, Knowledge Layer
materialization and immutable publication without building an LLM report. Completed jobs are
registered as ready analysis artifacts and selected for the standard context chat. The user
never selects a target relation; target resolution remains a backend/assistant responsibility.

Preparation job identifiers are kept in browser storage so progress resumes after a page reload.
No repository patch, commit, report generation or deployment is performed.
