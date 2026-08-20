# Knowledge Layer Core 0.59.39

## Legacy Cleanup Block 1

- Removed obsolete `task_suite_profile_semantics` and `legacy_fallback` tombstones from current materialization checks/results.
- Typed evidence/materialization behavior is unchanged; KLC continues to consume prepared evidence by canonical artifact contracts.
- No fallback to Task/Suite-era artifacts was introduced.
- `legacy_fallback_used` in logical/physical mapping is not part of this first cut; it is explicitly parked for the next compatibility audit because it is a distinct check and must be classified before removal.
- Historical validation snapshots were not rewritten.
