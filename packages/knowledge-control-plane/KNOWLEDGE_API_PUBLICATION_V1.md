# Knowledge API publication from analysis-ui

`analysis-ui` owns execution and raw job artifacts. `knowledge-api` owns stable
systems, immutable revisions, data-model queries and published reports.

## Publication sequence

1. Resolve the job's final `knowledge_layer` and optional `report_markdown` artifacts.
2. Ensure the stable system exists through `POST /api/knowledge/v1/systems`.
3. Publish an immutable revision through
   `POST /api/knowledge/v1/systems/{system_id}/revisions`.
4. Persist the returned `system_id` and `revision_id` in `JobDetails.publication`.

The producer payload uses `execution_id`, not a UI-specific field in the
Knowledge API contract. Repository provenance includes repository ID, current
Git revision, URI and dirty state when available.

## Failure semantics

- upstream HTTP/network failure fails stage `publication` only;
- analysis, Knowledge Layer and report artifacts remain available;
- `POST /api/v1/jobs/{job_id}/retry` with `from_stage=publication` reuses the
  final artifacts and repeats only the HTTP publication;
- a job with a successful external publication cannot be deleted while the
  transitional job-protection rule is active.

## Security

The client uses fixed contract paths and JSON requests through the Python
standard library. It does not execute shell commands, import server internals or
send protected LLM/Bitbucket credentials.
