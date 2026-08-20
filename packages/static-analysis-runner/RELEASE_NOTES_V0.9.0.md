# static-analysis-runner 0.9.0

- Removed the `workspace-knowledge-layer` package and external `workspace-knowledge` subprocess.
- Workspace profile mode now invokes `knowledge-layer-core` directly in-process.
- Removed `--workspace-knowledge-command` and all WKL version checks.
- `static-analysis-runner` is the sole supported CLI entry point for repository and workspace analysis.
- Knowledge Layer producer metadata now always identifies `knowledge-layer-core`.
