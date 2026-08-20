# Analysis UI 2.0.0a41

## Foreign Data Persistence master

- Added the user-facing pipeline `foreign-data-persistence-pipeline:v1` named **Хранение внешних данных**.
- The pipeline uses only the fixed runner suite `foreign-data-persistence` and passes `--suite-id`; no analysis-profile fallback is allowed.
- Repository and workspace execution are both supported.
- Knowledge materialization must publish capability `suite.fdp`; otherwise the job records an explicit profile mismatch.
- The fixed report profile is `foreign-data-persistence-report/v1`.
- Added a dedicated FDP mode to the workspace wizard with user-facing wording, a report focus and explicit treatment of unresolved chains as gaps.
- FDP revisions open without requiring data-model tables; report and standard chat remain available.
- Revision chat receives the originating pipeline identity and shows FDP-specific capabilities and example questions.
