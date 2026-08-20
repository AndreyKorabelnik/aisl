# Test results — 0.9.33

- full Runner suite: **85 passed**;
- deterministic snapshot unit regression: passed;
- two independent KLC topology builds from the same four real repository shards: passed;
- identical `snapshot_id`: passed;
- identical strict/extended `island_id`: passed;
- identical `topology_fingerprint`: passed;
- changed commit changes snapshot identity: passed;
- compileall and archive manifest validation: passed.

HTTP E2E facts remain unchanged from 0.9.32: 4 repositories, 3 system interactions, 8 boundary interactions, 4 strict islands and 1 extended island.
