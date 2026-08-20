# FDP AT900 test status — code-analyzer-core 0.43.9

- Focused overloaded-builder + container provenance tests: 2 passed.
- FDP and Java lineage regression set: 63 passed.
- Real AT900 resolver probe: five fields resolved from Kafka `SyncPushDeviceRequest` to the `forUpdateActual` persistence input.
- `compileall`: passed.
- Source manifest validation: passed.
- ZIP integrity: passed.

Known limitation: the storage-to-public-response half of the AT900 case is not included in this version.
