# analysis-ui 2.0.0a21

Iteration 24.4 completes frontend cleanup after removal of the alternate backend.

- `LegacyTaskView`/`LegacyTaskStatus` were replaced with `AnalysisJobView`/`AnalysisJobStatus`;
- the frontend projection uses canonical `job_id`;
- store and client methods use job terminology;
- the route prop is `jobId`;
- orchestration `/api/v1/**` and Knowledge API `/api/knowledge/v1/**` remain intentionally distinct.
