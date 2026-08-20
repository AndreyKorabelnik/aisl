# Test status — KLC 0.61.0a8

- Full KLC regression: 203 PASS / 8 SKIP.
- Targeted placeholder / producer / materialization-seed tests: PASS.
- Real UDDK targeted traversal: PASS; useful partial lineage exposed, unresolved fields remain explicit gaps.
- Real dictionary materialization traversal: PASS for five representative dictionary Gold misses.
- Real t_dim_client_team_type traversal: PASS; current/history terminal origins observed for sid and related fields.
- Whole-repository sql-target-source-mapping materialization exceeded the local 120s test budget in one diagnostic run; this is NOT reported as PASS or functional failure.
