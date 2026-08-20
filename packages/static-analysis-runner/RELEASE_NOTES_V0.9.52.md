# static-analysis-runner 0.9.52

## Generic storage and SQL execution

- Removed the old SQL-specific repository artifact route and its public dispatch surface.
- `storage-usage-evidence/v1` and `sql-analysis/v1` are planned and executed only through the generic Core evidence executor.
- `observed-storage-usage` and `sql-analysis` are executed only through the generic KLC materialization executor.
- Corrected source-snapshot compatibility so Java storage analysis and SQL-file analysis can coexist in one knowledge execution plan.
- No evidence-family or materialization-specific branch was added to production Runner code.
