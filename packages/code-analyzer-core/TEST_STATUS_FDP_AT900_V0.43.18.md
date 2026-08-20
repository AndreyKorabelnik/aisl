# Test status — FDP AT900 card factory — code-analyzer-core 0.43.18

## Automated tests

- Affected persistence/FDP tests: `72 passed`.
- New factory method-reference regression: passed.
- `compileall`: passed.
- Source manifest verification: passed.
- ZIP integrity verification: passed.

## Real AT900 source probe

`UpdatePprbCardProcessor.createCardUpdate` now publishes:

- `CardUpdate.account <- MigrateCardRq.data.financialProductId`;
- `CardUpdate.ucpId <- MigrateCardRq.data.epkId`;
- `CardUpdate.productId <- MigrateCardRq.data.productWay4Code`.

The `requests.stream().collect(Collectors.toMap(..., this::createCardUpdate, ...))`
projection resolves the same source paths for the map value fields.

This release intentionally stops at the factory/map boundary. The next step is
propagation through `Map.get -> modifiedCard -> toBuilder -> mergeCardInfos`.
