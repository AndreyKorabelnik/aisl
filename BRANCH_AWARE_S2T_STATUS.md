# S2T status

Status: **ACCEPTED CHECKPOINT / READY FOR CANONICAL PACKAGING**.

Accepted real insurance behavior:

- one human S2T row per target field per observed UNION/query branch;
- `t_dim_accrual.accrual_dt`: ASBS, SBS and SBSZH are separate rows;
- `t_dim_accrual.counterparty_id`: JOIN-key correlation prevents cross-branch SBS/SBSZH/ASBS/EKP fan-out;
- `T-src-f` contains only real calculation; structural UNION text is not emitted;
- raw `${$app...}` table placeholders are resolved through observed scoped configuration; environment variables remain partial when stand is not selected.

The implementation remains generic and confined to KLC composition plus a read-only exporter. Core is unchanged.
