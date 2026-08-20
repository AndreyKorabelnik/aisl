# static-analysis-runner 0.9.55 — SQL legacy path removal

- Removed taxonomy entries for the retired profile-controlled SQL sub-stages.
- The active SQL route is the registered generic Core analyzer producing `sql-analysis/v1` evidence, followed by KLC `sql-analysis` or `workspace-sql-catalog` materialization.
- No compatibility adapter, dual-read, dual-write or fallback to the removed SQL profile was added.
