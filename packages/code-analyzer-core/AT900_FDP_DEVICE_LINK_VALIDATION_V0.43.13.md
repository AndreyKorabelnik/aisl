# AT900 FDP DeviceLink validation — Core 0.43.13

Fresh canonical `source_to_storage_lineage` output confirms:

| External source | Physical target |
|---|---|
| `SyncPushDeviceRequest.clientId` | `DEVICE_LINK.CLIENT_ID` |
| `SyncPushDeviceRequest.deviceId` | `DEVICE_LINK.DEVICE_ID` |
| `SyncPushDeviceRequest.hmgUid` | `DEVICE_LINK.HMGUID` |
| `SyncPushDeviceRequest.loginId` | `DEVICE_LINK.LOGIN_ID` |
| `SyncPushDeviceRequest.phoneNumber` | `DEVICE_LINK.PHONE_NUMBER` |
| `SyncPushDeviceRequest.reason` | `DEVICE_LINK.REASON` |
| `SyncPushDeviceRequest.requestTime` | `DEVICE_LINK.UPDATE_TIME` |
| `SyncPushDeviceRequest.ucpId` | `DEVICE_LINK.UCP_ID` |

For all rows:

- source kind: `kafka_consumed`;
- source operation: `SyncPushDeviceConsumer.onReceive`;
- source payload: `SyncPushDeviceRequest`;
- evidence maturity: `confirmed`.

The catalogue no longer emits `dao_implementation_not_resolved` for `DeviceLinkServiceImpl.changeData → DeviceLinkDao.updateDeviceLink`.

An unrelated unresolved request remains for `pushInformHistoryDao.saveHistory`; it is not part of this vertical case.
