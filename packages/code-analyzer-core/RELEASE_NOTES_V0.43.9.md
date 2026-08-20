# code-analyzer-core 0.43.9

Version 0.43.9 continues the AT900 Foreign Data Persistence vertical regression.

## Changes

- Added bounded interprocedural provenance across method parameters and production call sites.
- Linked collection accessors used by persistence calls to mutator methods that populate the same backing collection.
- Resolved mutator arguments through signature-specific builder mappings.
- Propagated source fields through local aliases, collection elements, service/handler calls and Kafka ingress.
- Excluded test-code callers from canonical upstream provenance selection.
- Added a synthetic regression for `Kafka payload -> batch mutator -> accessor -> service`.

## AT900 validation

The resolver now maps the `SyncPushDeviceRequest` ingress to `DEVICE_LINK` write inputs for `clientId`, `deviceId`, `hmgUid`, `ucpId`, and `requestTime`.

## Scope

This iteration closes the source-to-storage half of the selected vertical case. Physical read projection and the path from `DEVICE_LINK` to `ClientDevicePair` / `POST /deviceIdList` remain for the next iteration.
