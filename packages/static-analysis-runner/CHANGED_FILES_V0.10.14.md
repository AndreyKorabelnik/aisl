# static-analysis-runner 0.10.14 — Legacy Cleanup Block 8

- Removed `static_analysis_runner/stage_taxonomy.py`, the obsolete Runner-owned reverse-engineering/classification of Core stages.
- Retained only Markdown rendering of Core-published Java derived-stage contracts, moved into `mechanism_catalog.py`.
- `mechanism-catalog` continues to consume `core_analysis_catalog/v1` as the single source of Core stage classification.
- Added a negative contract test that the parallel taxonomy module is absent and a CLI test proving Markdown is rendered from the official Core catalog.
