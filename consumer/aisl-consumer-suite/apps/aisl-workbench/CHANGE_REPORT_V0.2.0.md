# aisl-workbench 0.2.0

- Added Reports tab over independent `aisl-reporting` HTTP service.
- Workbench server now has a separate optional `/api/reporting/*` proxy configured by `AISL_REPORTING_URL`.
- Knowledge API proxy remains read-only.
- ReportRun request always sends the already pinned concrete `system_id` + `revision_id`.
- ReportRun metadata/content remain Reporting-owned and are not written to AISL.
