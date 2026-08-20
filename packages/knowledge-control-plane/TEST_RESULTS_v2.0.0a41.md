# Test results 2.0.0a41 — FDP master

Focused profile, API and frontend contracts: **36 passed**.

Pipeline regression block: **8 passed** covering:
- FDP repository pipeline;
- FDP workspace pipeline;
- exact suite invocation and absence of profile fallback;
- fixed FDP report profile;
- explicit contract conflict;
- system-description pipeline;
- data-model workspace pipeline;
- suite-only data-model rejection;
- revision publication.

Additional checks:
- TypeScript and Vue script syntax: passed;
- frontend orchestration boundary check: passed;
- Python `compileall`: passed;
- OpenAPI generation: passed;
- source manifest verification: passed;
- ZIP integrity: passed.

Production frontend build was not run because the complete npm dependency set is not available in the local environment.
