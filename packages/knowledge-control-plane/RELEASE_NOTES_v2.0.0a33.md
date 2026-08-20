# Analysis UI 2.0.0a33

- Prepared assistant contexts now pass pinned PDM system/revision references to Knowledge Assistant 0.14.0.
- Added the optional PDM file path to the existing context-preparation wizard.
- Added a PDM knowledge-only full pipeline: physical model analysis, typed Knowledge Layer materialization and immutable publication, without report generation.
- PDM remains optional and does not determine SQL read/write roles.
- Target relation selection remains automatic.
- Publication now deterministically selects `knowledge-layer.duckdb` instead of a later-registered JSON sidecar and publishes it as `application/vnd.duckdb`.
