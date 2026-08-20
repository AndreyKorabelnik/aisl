# code-analyzer-core 0.44.18

Legacy Cleanup Block 2 removes the obsolete `dual_write="not_supported"` anti-legacy marker from current Core contracts and typed evidence.

## What changed

- Removed `dual_write` from Core evidence runtime assessment, prepared evidence policies/manifests/provenance, and current target contract output.
- No dual-write implementation, compatibility alias, default injection, or replacement marker was added.
- Typed semantic dispatch remains `artifact_kind + schema_version`.
- Historical validation/release snapshots remain unchanged as provenance.

No analyzer semantics or evidence extraction logic changed.
