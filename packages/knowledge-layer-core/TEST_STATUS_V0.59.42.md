# Test status — knowledge-layer-core 0.59.42

- Focused KLC contract/materialization suite: **14 passed**.
- Real workspace-data-model build smoke: **1 passed**.
- Negative cleanup checks: removed compatibility schema alias is absent from public exports; obsolete `fetch_size` parameter is absent; legacy validation tombstones are absent from active builders.
- Compileall: **passed**.
- Import/materialization registry smoke: **passed**, 19 materializations registered.
- Source manifest verification: **passed**.
- Full multi-module regression intentionally not run for this KLC-only compatibility-surface cut.
