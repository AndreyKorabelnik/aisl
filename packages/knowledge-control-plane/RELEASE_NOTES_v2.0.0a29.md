# Analysis UI 2.0.0a29

Extends the prepared-context wizard with reuse of existing successful analysis jobs.
The UI lists only succeeded jobs that already have an immutable Knowledge API publication
and a registered Knowledge Layer DuckDB. Importing such a job creates an analysis-artifact
reference without re-running analysis, copying the DuckDB, or publishing another revision.

The existing manual server-path registration remains available as a second mode. The user
still does not select a target table; automatic target and SQL insertion-point resolution
remain backend and Knowledge Assistant responsibilities.
