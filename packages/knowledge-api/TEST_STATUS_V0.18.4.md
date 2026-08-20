# Test status — 0.18.4

- Full Knowledge API test suite: 58 passed.
- Real HTTP target-column-lineage (`epk_client`): 200, 116 paths / 86 columns / 7 gaps.
- Real HTTP field-calculation: 4/4 representative fields returned 200 and `complete`.
- compileall: OK.
- OpenAPI export: regenerated and tested.
- ZIP integrity: OK.

Runtime note: workflow-resolved lineage requires a KLC artifact produced by knowledge-layer-core 0.59.17 or later. Existing direct-write lineage remains supported for older compatible artifacts.
