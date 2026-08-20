# analysis-ui 2.0.0a9 — workspace and UCP frontend

Iteration 9 makes the existing workspace backend accessible through the browser UI.

## User-visible capabilities

- switch between single-repository and workspace analysis on the home page;
- discover multiple local repositories or Bitbucket URLs;
- select repository membership and create/update persistent workspaces;
- apply a UCP preset (`workspace_id=ucp`, `system_id=ucp`, `data-model-pipeline:v1`);
- launch a full workspace pipeline and publish a stable system revision;
- browse published systems;
- inspect table catalogs, fields, keys, relationships and JOIN metadata;
- open Markdown reports and historical system revisions;
- jump from a completed workspace job to the published system.

## Production serving

The FastAPI application now serves SPA entry points for `/systems` and
`/systems/{system_id}` in addition to `/` and `/analysis/{job_id}`.

## Visual contract

Existing repository form, report renderer, timeline, progress and history components remain
identical to the UI 1.4.7 visual baseline. The intentional shell/workspace/system additions are
pinned separately in `docs/frontend/workspace-visible-sections.sha256`.
