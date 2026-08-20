# code-analyzer-core 0.44.20 — Legacy Cleanup Block 9

Removed the obsolete portfolio/workspace input compatibility surface from Core evidence access.

- `export_manifest()` is repository `static-analysis-output` only; removed `workspace` / workspace-only `repo_id` input and unreachable implementation.
- Removed old `workspace_summary`, `repo_summary`, `workspace_search` evidence tools.
- Removed `workspace_path` from the generic Core evidence-access request boundary and from static evidence tool contracts.
- Removed old `workspace_manifest.json` field-flow resolution branch.
- Removed `WORKSPACE_CONTRACT_VERSION` alias and unused `resolve_repository_static_output()` helper.
- Removed result tombstone `workspace_summary=None` from repository analyses.
- Updated current Core contract snapshots and added negative legacy-contract tests.
