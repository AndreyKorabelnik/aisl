# static-analysis-runner 0.9.9

## Workspace source manifest

- Added `--selected-repositories-manifest` for explicit repository paths.
- The manifest uses schema `selected_repository_sources/v1`.
- Repository paths are resolved and validated without symbolic links.
- Existing `--selected-repositories-root` remains available for direct child directories.
- Candidate selection is skipped for both preselected source modes.

This fixes the orchestration boundary where `analysis-ui` previously created symbolic links that the runner correctly rejected.
