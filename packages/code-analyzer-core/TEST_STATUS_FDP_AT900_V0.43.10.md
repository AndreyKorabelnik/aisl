# FDP AT900 test status — code-analyzer-core 0.43.10

- Focused JOOQ read / container provenance / overload tests: 3 passed.
- FDP and Java lineage regression set: 64 passed.
- Real AT900 probe: `DEVICE_LINK` physical read, four selected columns and `DeviceLinkRecord` confirmed.
- `compileall`: passed.
- Source manifest validation: passed.
- ZIP integrity: passed.

Known limitation: record-to-response projection and the multi-hop outward path are not yet resolved.
