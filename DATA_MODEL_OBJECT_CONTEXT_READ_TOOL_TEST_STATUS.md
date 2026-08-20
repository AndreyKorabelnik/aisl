# Data Model Object Context Read Tool — Test Status

Date: 2026-08-17

## Completed suites

- Prepared Knowledge Runtime full package suite: **14/14 PASS**.
- Knowledge Integration full package suite: **20/20 PASS**.
- Knowledge API contract suite: **12/12 PASS**.
- Knowledge API declared-data-model API suite: **9/9 PASS**.
- Knowledge API affected consumer/publication subset (`llm_integration_profile`, CLI, consumer runtime boundary, supported runtime layout, publication builder): **14/14 PASS**.
- Real UCP HTTP smoke against the published `ucp-data-model` revision: **PASS**.
  - Knowledge API reports version `0.38.0`.
  - exact `Individual` object resolved from the published revision;
  - object-context response contains 52 fields and 41 declared relationships;
  - `birthPlace` targets `com.sbt.bm.ucp.retail.model.individual.BirthPlace`;
  - because this revision publishes declared-model knowledge only, `storage_context.status = not_available` and no storage/physical join is guessed.
- Real UCP `data-model/v1` Consumer Kit generation: **PASS** with 5 tools including `get_data_model_object_context`.

## Non-results / limitations

- A full `knowledge-api` package regression was started but did not finish within 240 seconds. It emitted 19 completed test markers before timeout. This run is **not** classified as PASS or FAIL.
- Earlier combined test invocations that timed out are likewise not counted as PASS.
- Full framework regression was not run. Core, Runner, KLC, Reporting, KCP and AISL Contract behavior were unchanged by this increment.
