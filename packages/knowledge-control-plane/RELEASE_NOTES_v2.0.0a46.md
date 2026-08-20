# Analysis UI 2.0.0a46

- Adds backend-generated CLI preview to the **Advanced** section of repository and workspace masters.
- Uses the same normalized `JobCreateRequest` builder for preview and real job submission.
- Shows the complete planned external command sequence, including remote `git clone`/`git pull`, static analysis, Knowledge Layer materialization and reporting stages when applicable.
- Displays working directories, required environment variable names, runtime placeholders and the normalized API request.
- Adds copy actions for an individual command and for the full sequence.
- Redacts secret values and keeps preview side-effect free at the job/runtime-artifact level: no job, checkout, credential helper or workspace-selection manifest is created.
- Adds `POST /api/v1/jobs/preview` to the canonical orchestration API and generated OpenAPI document.
