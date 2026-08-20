# knowledge-api 0.30.15

- Adds revision-bound `GET /systems/{system_id}/foreign-data-persistence/guidance`.
- The endpoint is a deterministic consumer projection over the existing KLC `persistence-lineage` product; it creates no lineage, ownership, legal FDP or risk semantics.
- It preserves KLC path/case summaries and interpretation policy while bounding path, case, storage-summary and evidence presentation and omitting heavy `raw_fact` payloads.
- Confirmed cases are selected first for actionability but their KLC status is copied verbatim; unresolved/candidate states and missing links remain visible.
- Aligns the package dependency on `knowledge-integration==0.1.14`.
