# static-analysis-runner 0.10.10 — Legacy Cleanup Block 1

The current Runner contracts no longer carry tombstone fields describing removed Task/Suite-profile semantics or a disabled legacy fallback.

- Removed `task_suite_profile_semantics` and `legacy_fallback` from current evidence requests, input inventory, execution plan, materialization execution and knowledge execution result.
- Updated active JSON schemas in place; backward-compatibility readers/adapters were not added.
- Execution validation still rejects `dual_write` when it is not `not_supported`; that separate compatibility control is intentionally outside this cut.
- Generic Core dispatch, KLC materialization dispatch and capability publication semantics are unchanged.
- Historical validation snapshots remain unchanged.
