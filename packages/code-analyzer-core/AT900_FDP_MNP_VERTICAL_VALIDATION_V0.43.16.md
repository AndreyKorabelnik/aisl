# AT900 FDP MNP vertical validation — code-analyzer-core 0.43.16

Repository: AT900 client-profile, 1038 files.
Fresh suite result: `completed`; no previous result was reused.

Process status:

- foundation: 22.020 s;
- flow-lineage: 37.649 s;
- persistence-lineage: 17.524 s;
- timeouts: 0;
- stack dump requests: 0.

Confirmed source-to-storage:

- `KafkaMNPConsumer.onReceiveMessage`;
- `PhoneMNPEvent.phone.operator.operatorId`;
- `PHONE.OPERATORID`;
- all source/persistence/field/physical/end-to-end-to-storage dimensions confirmed.

Confirmed storage-to-access:

- physical read: `PHONE.OPERATORID`;
- response field: `MbClientProfileExtendedResponse.profiles.operatorId`;
- external boundary: `POST /mbClientProfileExtended`;
- storage read, access boundary, field mapping and storage-to-access lineage confirmed;
- missing links: none.
