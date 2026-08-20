# analysis-ui 2.0.0a5

Iteration 5 enables protected remote-repository checkout and durable multi-stage pipelines.

## Added

- runtime-owned checkout area under `outputs/ui/repositories`;
- Git/Bitbucket checkout through argv execution without a shell;
- `GIT_ASKPASS` authentication using protected environment values;
- built-in `system-description-pipeline:v1` and `data-model-pipeline:v1` profiles;
- durable pipeline stages: checkout, static analysis, Knowledge Layer materialization and reporting;
- per-stage status, timestamps, progress and artifact counts in `JobDetails` and SSE status events;
- stage-prefixed artifact paths to avoid collisions between analysis, Knowledge Layer and report outputs;
- retry from `knowledge_materialization` or `report_build` using artifacts from the previous job;
- remote and workspace pipeline E2E regression tests.

## Security

- repository URLs with embedded credentials are rejected;
- Bitbucket tokens are never persisted in SQLite, job parameters, command previews or logs;
- checkout paths are deterministic children of the runtime root;
- failed partial clones are removed only when they match the runtime-owned checkout path;
- refresh failures never delete an existing valid checkout;
- checkout ownership marker is stored inside `.git`, outside analyzed source content.

## Preserved

- all six data-model endpoints remain outside generic API ownership;
- all 20 Vue template/style sections remain identical to UI2 1.4.7;
- completed analysis and Knowledge Layer artifacts remain available when reporting fails;
- standalone repository, workspace, materialization and reporting jobs continue to work.

## Remaining capability gate

- generic assistant execution is still unavailable; conversation persistence remains implemented.
