# AT900 FDP MNP validation — code-analyzer-core 0.43.15

Repository: AT900 client-profile, 1038 files.

Fresh suite result: `completed`. Previous output was not reused.

- foundation: 25.060 s;
- flow-lineage: 45.099 s;
- persistence-lineage: 21.040 s;
- timeouts: 0;
- stack dump requests: 0.

Canonical `source_to_storage_lineage` now contains:

- source operation: `KafkaMNPConsumer.onReceiveMessage`;
- source payload: `PhoneMNPEvent`;
- source field: `phone.operator.operatorId`;
- storage target: `PHONE`;
- storage field: `OPERATORID`;
- source boundary: confirmed;
- physical storage: confirmed;
- field mapping: confirmed;
- end-to-end trace to storage: confirmed;
- source inspection required: false.
