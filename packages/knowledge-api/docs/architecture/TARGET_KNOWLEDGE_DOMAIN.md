# Knowledge API domain boundary

`knowledge-api 0.6.0` is the canonical public service for published analysis results.

## Owned resources

- systems;
- active and historical revisions;
- Knowledge Layer artifact references;
- prepared reports;
- tables, fields, keys, relationships and join metadata;
- publication provenance.

## Explicitly not owned

- Git repositories and workspace editing;
- analysis jobs and subprocess execution;
- logs and diagnostics bundles;
- LLM execution configuration;
- content-addressed analysis reuse.

## Contract

The only public namespace is `/api/knowledge/v1`. Publication is an idempotent write operation keyed by system ID and artifact identity. Read endpoints accept an optional revision ID and default to the active revision.
