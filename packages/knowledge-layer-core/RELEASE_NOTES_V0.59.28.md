# knowledge-layer-core 0.59.28

FDP read-side quality cleanup; persistence materialization semantics are unchanged.

The FDP query service now builds its unfiltered path catalog strictly from the two canonical path artifacts. Previously, any other persistence-lineage payload record could be interpreted as storage→access when `direction` was omitted, inflating path/case counts and polluting report summaries with DAO/JOOQ/test helper observations.

Real AT900 result with Core 0.44.16 evidence:

- FDP paths: 2311 → 781;
- canonical source→storage: 529;
- canonical storage→access: 252;
- mechanical cases: 2499 → 969;
- confirmed exact same-data cases remain 8.

No new lineage is inferred and no confirmed case is removed by this cleanup.
