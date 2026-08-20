# Analysis UI 2.0.0a31

Adds explicit analysis-purpose metadata to static profiles. The orchestration API now exposes
`analysis_purposes` with `source_model`, `sql_datamart` and/or `pdm`, derived from declared
profile stages and output contracts or from an explicit `analysis_ui.purposes` declaration.
Profile filenames are not used for classification.

This contract lets the prepared-context wizard choose suitable source and datamart profiles
without asking users for technical profile IDs or relying on frontend name heuristics.
