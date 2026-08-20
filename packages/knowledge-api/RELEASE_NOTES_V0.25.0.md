# Knowledge API 0.25.0

## Changes
- Added the revision-bound `foreign-data-persistence/query` read surface.
- The API delegates FDP query semantics to KLC `ForeignDataPersistenceQueryService`.
- Supported queries: path list/detail, mechanical cases and landscape.
- Requires canonical `persistence-lineage` knowledge with `workspace.fdp-paths`.
- No business/legal FDP decision logic or fallback knowledge source was added.

## Validation
- Full test suite: 70 passed.
- Real AT900 prepared-revision HTTP/Assistant acceptance passed.
