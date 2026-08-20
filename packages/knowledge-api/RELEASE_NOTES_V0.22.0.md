# Knowledge API 0.22.0

- Adds thin revision-bound System Interactions read endpoints over existing KLC query contracts.
- Exposes interaction summaries, repository boundaries, execution contexts, field contracts, diagnostics, and optional repository coverage.
- Each surface selects knowledge strictly by published capability; field contracts and coverage do not fall back to the system-interactions artifact.
- No interaction matching, semantic classification, or orchestration logic was added to Knowledge API.
