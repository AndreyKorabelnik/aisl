# code-analyzer-core 0.44.17

Legacy Cleanup Block 1 removes obsolete anti-legacy contract markers from the current Core evidence boundary.

## What changed

- Removed `task_suite_profile_semantics="not_used"`, `legacy_task_suite_profile_semantics="not_used"`, and `legacy_fallback="not_supported"` from current typed evidence/profile/target-contract outputs.
- No compatibility alias, default injection, dual-read, or replacement tombstone was introduced.
- Canonical dispatch remains `artifact_kind + schema_version` through the Core Evidence Runtime.
- `dual_write="not_supported"` is intentionally unchanged in this block and will be assessed separately with other compatibility controls.
- Historical validation/release snapshots were not rewritten.

No analyzer semantics or evidence extraction logic changed.
