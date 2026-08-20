# AT900 FDP status cleanup validation — Core 0.43.17

The compact source-to-storage catalog was rebuilt from the full AT900 client-profile repository.

## Result

| Metric | Value |
|---|---:|
| source-to-storage rows | 505 |
| confirmed | 58 |
| unresolved | 447 |
| confirmed rows with stale missing links | 0 |
| status/maturity mismatches | 0 |

## Confirmed MNP row

`PhoneMNPEvent.phone.operator.operatorId -> PHONE.OPERATORID`

- `lineage_status=confirmed`
- `missing_links=[]`
- segment status: confirmed
- field mapping status: confirmed
- inline mapping status: confirmed

## Confirmed device row

`SyncPushDeviceRequest.deviceId -> DEVICE_LINK.DEVICE_ID`

- `lineage_status=confirmed`
- `missing_links=[]`
- segment status: confirmed
- field mapping status: confirmed
- inline mapping status: confirmed

The analyzer still makes no business own/foreign classification and no risk decision.
