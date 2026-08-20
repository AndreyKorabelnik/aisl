# static-analysis-runner 0.10.11

Legacy Cleanup Block 2 removes the obsolete `dual_write="not_supported"` marker from current orchestration contracts.

## What changed

- Removed `dual_write` from evidence execution, knowledge planning, materialization execution, data-model discovery, and knowledge execution semantic-policy payloads.
- Replaced the dedicated tombstone check with exact validation of the current canonical semantic-policy fields; an old result that reintroduces `dual_write` is rejected.
- Removed `dual_write` from current execution-plan/result JSON schemas.
- Canonical Core/KLC registry dispatch and capability publication checks remain unchanged.
- No compatibility read/write branch was introduced.
