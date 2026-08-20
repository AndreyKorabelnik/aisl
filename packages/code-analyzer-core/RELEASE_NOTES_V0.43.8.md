# code-analyzer-core 0.43.8

Version 0.43.8 begins the AT900 Foreign Data Persistence vertical regression.

## Changes

- Builder and `toBuilder()` field mappings are extracted from every source-declared Java overload instead of the single legacy `Class.method` body.
- `builder_field_mapping` now includes `operation_signature`, allowing deterministic overload selection downstream.
- Added a regression test for overloaded `updateBy(String)` and `updateBy(SyncPushDeviceRequest)` methods.

## Scope

This iteration restores the missing `SyncPushDeviceRequest -> DeviceLinkWrapper` mapping evidence. It does not yet connect the resulting object through `SyncDevicesBatch` to `DEVICE_LINK`; that is the next iteration.
