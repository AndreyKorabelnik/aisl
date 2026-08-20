# Analysis UI 2.0.0a79

## Repository/workspace Data Model master

- `data-model-v1` now means code-declared model extracted from one or more repositories.
- One generic `repositories` workspace contract handles both a single repository and N repositories.
- The master produces only `code-declared-data-model`; it no longer requests `effective-data-model`, PDM, SQL inputs, or the composite `data-model-report/v1`.
- Chat opens with declarative Assistant policy `data-model/v1`.
- `data-model-attribute-extension-v1` remains a separate UCP + SQL datamart + PDM product and is unchanged.
- Runtime catalogs are pinned to Core 0.44.16 / Runner 0.10.9 / KLC 0.59.37.
