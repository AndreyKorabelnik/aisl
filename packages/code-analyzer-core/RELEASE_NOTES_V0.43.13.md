# code-analyzer-core 0.43.13

## FDP custom DAO update provenance

The persistence profile now follows external payload fields through a custom DAO `update` boundary when the DAO implementation contains source-proven JOOQ write mappings.

The promotion is deliberately strict:

- a method name such as `update*` is not sufficient;
- the receiver must be a `custom_dao_boundary`;
- the source-declared DAO implementation must resolve;
- at least one DAO parameter must map to a concrete JOOQ table and write column;
- delete/remove operations are never promoted by this rule.

This closes the AT900 vertical source path:

`SyncPushDeviceRequest → DeviceLinkWrapper → SyncDevicesBatch → DeviceLinkServiceImpl → DeviceLinkDao → DEVICE_LINK`.

The canonical FDP catalogue now contains confirmed Kafka-to-storage mappings for `CLIENT_ID`, `DEVICE_ID`, `HMGUID`, `LOGIN_ID`, `PHONE_NUMBER`, `REASON`, `UPDATE_TIME` and `UCP_ID`.

The change also removes the contradictory `dao_implementation_not_resolved` request when the same DAO implementation has already been resolved to physical JOOQ writes.

No AT900-specific class, method, table or field names are present in the resolver.
