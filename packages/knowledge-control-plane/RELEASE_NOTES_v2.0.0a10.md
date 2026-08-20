# analysis-ui 2.0.0a10 — content-addressed stage reuse

Iteration 10 adds safe automatic reuse for unchanged repository and workspace runs while
preserving an explicit full-rebuild mode.

## Default behaviour

New jobs use `reuse_policy=reuse_if_unchanged`. The backend computes independent fingerprints
for static analysis, Knowledge Layer materialization and report rendering. A stage is reused
only when its fingerprint matches a completed cached stage and the required artifact still
exists.

## Fingerprint inputs

- repository commit and dirty working-tree content;
- every repository and ordered membership of a workspace;
- analysis and reporting profile content;
- configured CLI executable identity and reported version;
- stage-relevant parameters;
- report response-file content when supplied.

## User controls

- **Repeat LLM/report** (`force_llm_rerun`) reuses analysis and Knowledge Layer but renders the
  report again;
- **Force full rebuild** (`reuse_policy=force_rebuild`) bypasses all stage reuse and refreshes a
  materialized remote checkout before running.

## Provenance

`JobDetails.reuse.reused_stages` records the source job and fingerprint for every reused stage.
Cache records are durable in SQLite and are removed automatically with their owning jobs.
