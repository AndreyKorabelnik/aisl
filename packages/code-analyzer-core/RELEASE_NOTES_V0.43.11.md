# code-analyzer-core 0.43.11

## Changes

- Added observed JOOQ-record getter to DTO-constructor position mappings.
- Added bounded result-propagation traversal from physical DAO reads through service methods to outward REST/message boundaries.
- Preserved nested response paths for collection/map response fields.
- Prevented DAO/helper return values from being misclassified as confirmed outward access.
- Added a full regression for `JOOQ read -> record -> DTO -> service -> REST response`.

## AT900 validation

Confirmed path:

`DEVICE_LINK -> DeviceLinkRecord -> ClientDevicePair -> DevicesByPhonesResponse.phoneToDevice -> POST /deviceIdList`

Confirmed field mappings:

- `CLIENT_ID -> phoneToDevice.clientId`
- `DEVICE_ID -> phoneToDevice.deviceId`
- `UCP_ID -> phoneToDevice.ucpId`

## Scope

Core now provides both halves of the selected vertical case. The next step is a fresh FDP suite/KLC materialization to verify mechanical source-to-storage plus storage-to-access joining.
