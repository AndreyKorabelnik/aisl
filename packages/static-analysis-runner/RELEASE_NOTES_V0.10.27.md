# static-analysis-runner 0.10.27

## Block E — Core-owned preflight applicability selection

- Extends the existing generic repository source snapshot with observed file extensions alongside languages and file count.
- Evaluates only the declarative `preflight_planning.applicability` predicate supplied by the Core evidence contract catalog.
- Automatic `produce_if_missing` evidence may be omitted only when the Core predicate is formalized and the source snapshot is observed `not_applicable`.
- `unresolved` applicability remains visible and preserves execution eligibility; it never becomes a hard skip.
- Explicit/required evidence is never silently optimized away: observed non-applicability becomes a blocking diagnostic and remains visible as an unsatisfied required input.
- No concept inference, analyzer-code inspection, second registry or second planner is introduced in Runner.
