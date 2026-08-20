# AT900 FDP mechanical bridge validation — KLC 0.53.3

The fresh AT900 Knowledge Layer contains:

- eight `SyncPushDeviceRequest → DEVICE_LINK` source paths;
- one confirmed `DEVICE_LINK → ServerController.findDevicesByPhones` access path;
- the REST endpoint `/deviceIdList` in the underlying access evidence.

Exact source fields written:

`CLIENT_ID`, `DEVICE_ID`, `HMGUID`, `LOGIN_ID`, `PHONE_NUMBER`, `REASON`, `UPDATE_TIME`, `UCP_ID`.

Exact fields later read into the public response:

`CLIENT_ID`, `DEVICE_ID`, `UCP_ID`.

Mechanical result:

```text
storage object: DEVICE_LINK
field overlap: CLIENT_ID, DEVICE_ID, UCP_ID
same_data_end_to_end_status: confirmed
business_fdp_decision: not_assigned
risk_decision: not_assigned
```

This is field-overlap proof across two static-analysis segments, not a business classification that the data is foreign or improperly persisted.
