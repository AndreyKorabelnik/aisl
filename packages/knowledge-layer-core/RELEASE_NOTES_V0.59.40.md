# knowledge-layer-core 0.59.40

Legacy Cleanup Block 2 removes the obsolete `dual_write="not_supported"` marker from current KLC materialization checks.

## What changed

- Removed `dual_write` from subject knowledge, interaction knowledge, repository value-flow, and value-flow build checks.
- Materialization behavior and typed evidence requirements are unchanged.
- `legacy_fallback_used` in logical/physical mapping is deliberately not changed in this cut and remains a separately classified candidate.
- Historical validation snapshots remain unchanged.
