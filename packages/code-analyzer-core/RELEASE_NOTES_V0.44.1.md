# code-analyzer-core 0.44.1 — SQL legacy path removal

- Removed the retired `sql-mart-lineage` profile and fixed SQL stage pipeline.
- SQL change analysis now requests typed `sql-analysis/v1` evidence through the generic evidence runtime.
- Removed the uncalled `run_sql_analysis` wrapper and the old repository aggregate writer.
- Removed mart-specific aggregate computation and publication surfaces; canonical statements, relations, dependencies, joins, lineage, placeholders and gaps remain.
- Removed the redundant DB-schema scan from the SQL analyzer. DB schema analysis remains a separate typed analyzer.
- Removed dual-read of retired SQL aggregate files from git-change delta construction.
- Profiles with typed evidence requirements no longer need a synthetic stage pipeline.
