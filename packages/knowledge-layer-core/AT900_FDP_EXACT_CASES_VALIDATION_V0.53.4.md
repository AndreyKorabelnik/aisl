# AT900 FDP exact-case validation — KLC 0.53.4

## MNP operator

The same table contains many independent write and read scenarios. KLC now emits
three separate `OPERATORID` path-pair candidates for the MNP source:

- two unresolved access paths;
- one confirmed path to `MbClientProfileController.mbClientProfileExtended`.

The confirmed case has:

- storage object: `PHONE`;
- storage field: `OPERATORID`;
- source: `KafkaMNPConsumer.onReceiveMessage`;
- access: `MbClientProfileController.mbClientProfileExtended`;
- overlap: exactly `OPERATORID`;
- missing links: none.

`TOKENID` and `PHONEBLOCKCODE` are not included in this case.

## Device link

Three independent confirmed exact cases exist for:

- `CLIENT_ID`;
- `DEVICE_ID`;
- `UCP_ID`.

They share the same source/access scenario but remain field-specific evidence cases.

## Policy

Table-level aggregation is summary-only. It cannot be used as proof that all
fields written to a table are exposed by every access path.
