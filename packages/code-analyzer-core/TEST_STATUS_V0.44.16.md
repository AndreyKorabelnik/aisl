# Test status — code-analyzer-core 0.44.16

- Focused FDP/persistence regression: **77 passed**.
- Real AT900 `persistence-lineage-evidence` run: **PASS**, 1038 files, 7104 persistence facts, 529 source→storage lineages.
- Real AT900 validation:
  - false `SyncPushDeviceRequest.phoneNumber/loginId/reason` attribution removed;
  - `SpreadProfileRq.id → UCP_PHONE_2.UCP_ID` confirmed;
  - `SpreadProfileRq.version → UCP_PHONE_2.LAST_EVENT_ID` confirmed;
  - MNP confirmed path preserved;
  - PPRB and NotificationChannel remain partial where the same observed-fact composition does not prove an end-to-end path.
- `compileall`: PASS.
