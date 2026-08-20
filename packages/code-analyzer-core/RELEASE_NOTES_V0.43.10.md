# code-analyzer-core 0.43.10

## Changes

- Added physical read extraction for JOOQ `select(...).from(TABLE)` chains.
- Preserved selected physical columns and `fetchInto(Record.class)` result type.
- `read_from_storage` now uses observed selected fields and the observed JOOQ record type.

## AT900 validation

`ClientProfileDaoImpl.getDevicesByPhones` is now represented as a confirmed physical read from `DEVICE_LINK` with fields `DEVICE_ID`, `PHONE_NUMBER`, `CLIENT_ID`, `UCP_ID` and result type `DeviceLinkRecord`.

## Scope

This iteration establishes the physical read. Constructor projection to `ClientDevicePair` and the multi-hop path to `POST /deviceIdList` remain for the next iteration.
