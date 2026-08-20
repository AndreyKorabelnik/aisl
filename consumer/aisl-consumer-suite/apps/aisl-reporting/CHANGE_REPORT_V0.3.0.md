# aisl-reporting 0.3.0

- Added standalone HTTP Reporting Service and reporting-owned persistent ReportRun lifecycle.
- Every service run requires explicit `system_id + revision_id + profile`.
- ReportRun identity/lifecycle is independent from AISL revision identity.
- Added profile discovery, run list/detail, report content and dataset endpoints.
- Renderer configuration is server-side; service requests cannot inject arbitrary endpoints.
- Existing CLI prepare/build behavior remains; no framework integration was reintroduced.
