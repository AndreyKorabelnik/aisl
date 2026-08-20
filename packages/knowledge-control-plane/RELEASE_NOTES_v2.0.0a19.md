# analysis-ui 2.0.0a19

## Workspace execution compatibility

- Replaced the symbolic-link workspace staging directory with a `selected_repository_sources/v1` manifest containing validated real repository paths.
- Workspace commands now use `static-analysis-runner workspace --selected-repositories-manifest`.

## Responsive job startup

- Repository/workspace content fingerprints are calculated in a worker thread instead of blocking the FastAPI event loop.
- A successful `POST /api/v1/jobs` is returned to the UI immediately without synchronous log/artifact hydration.
- Long repository fingerprinting no longer produces the misleading frontend error `timeout of 30000ms exceeded`.
