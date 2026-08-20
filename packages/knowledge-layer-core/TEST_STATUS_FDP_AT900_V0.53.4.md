# Test status — FDP AT900 / knowledge-layer-core 0.53.4

## Automated tests

- exact FDP query tests: 3 passed;
- suite/FDP query tests: 8 passed, 1 optional real-UCP test skipped;
- compileall: passed;
- source manifest: passed;
- ZIP integrity: passed.

## Real AT900 query validation

Knowledge Layer input: current AT900 FDP database built from Core 0.43.16 evidence.

Exact case results:

- cases: 945;
- cases with both source and access paths: 163;
- confirmed exact same-data cases: 11;
- storage summaries: 85.

`PHONE.OPERATORID` MNP source produces three separate path-pair cases:

- two unresolved internal/service access candidates;
- one confirmed external path to `MbClientProfileController.mbClientProfileExtended`.

The confirmed case contains only `OPERATORID`; it no longer includes `TOKENID` or `PHONEBLOCKCODE` from unrelated paths.

`DEVICE_LINK` has three confirmed independent cases:

- `CLIENT_ID`;
- `DEVICE_ID`;
- `UCP_ID`.

Each points from a `SyncPushDeviceRequest` source path to the concrete device-list access path.
