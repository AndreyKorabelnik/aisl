# Test status — Knowledge Layer Core 0.61.0a23

- Targeted regression: 9 passed.
- Real insurance validation: `t_dim_accrual.counterparty_id` branch correlation PASS on existing SQL knowledge; SBS→SBS only, SBSZH→SBSZH only, ASBS→ASBS only.
- Rebuilt only `workflow_target_lineage` and `sql-target-source-mapping`; Core/PDM/full SQL ingest not rerun.
- Full suite intentionally not run for this quick hotfix.
