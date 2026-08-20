# Test status — FDP AT900 / code-analyzer-core 0.43.17

## Automated tests

- focused confirmed custom-DAO provenance regression: passed;
- affected FDP/persistence suite: 73 passed;
- compileall: passed;
- source manifest validation: passed;
- ZIP integrity: passed.

## Real AT900 validation

Repository files: 1038.

Fresh flow-lineage analysis completed and produced:

- 57,264 field occurrences;
- 43,962 field-flow edges;
- 531 field-lineage facts.

Fresh persistence-lineage analysis completed and produced:

- 7,073 persistence facts;
- 505 source-to-storage lineage rows.

Canonical status distribution:

- confirmed: 58;
- unresolved: 447;
- confirmed rows with non-empty `missing_links`: 0;
- rows where `lineage_status` differs from `evidence_maturity_level`: 0.

Validated examples:

- `PhoneMNPEvent.phone.operator.operatorId -> PHONE.OPERATORID` is confirmed;
- `SyncPushDeviceRequest.deviceId -> DEVICE_LINK.DEVICE_ID` is confirmed;
- both have empty missing links and confirmed inline mappings.

No partial lineage was upgraded merely because a target field was observed.
