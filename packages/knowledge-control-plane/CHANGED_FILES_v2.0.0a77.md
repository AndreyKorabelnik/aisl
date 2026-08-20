# Changed files — Analysis UI 2.0.0a77

## Purpose

Synchronize the UI with the current generic Knowledge Product execution and universal prepared-revision consumer architecture. This release does not add scenario-specific execution runtimes.

## Generic source context

- `src/analysis_ui/api/generic_v1/models.py`
  - added `ProfileSourceMode` (`repository`, `repositories`, `knowledge_revisions`);
  - `ProfileInfo` now exposes `source_mode` and optional `assistant_profile_id`;
  - `JobTarget` supports `repository_ids[]` for source-backed workspaces;
  - repository, repository-list and published-revision inputs are mutually exclusive;
  - `assistant_profile_id` accepts canonical Assistant profile ids containing `/`.
- `src/analysis_ui/runtime/pipeline.py`
  - one generic pipeline now supports single-repository, multi-repository source workspace and published-revision workspace;
  - source-backed workspaces run checkout/Core/KLC through the existing Runner path;
  - revision-backed workspaces continue to skip Core.
- `src/analysis_ui/runtime/commands.py`
  - input inventory passes any number of repository paths through repeated Runner `--repository` arguments.
- `src/analysis_ui/runtime/jobs.py`
  - one checkout/execution path handles all selected source repositories;
  - existing-knowledge input resolution is used only for revision-backed workspaces;
  - report requests are rejected explicitly when a selected profile has no report profile.
- `src/analysis_ui/runtime/one_shot.py`, `src/analysis_ui/cli.py`
  - one-shot execution supports repeated `--repository` using the same source-mode contract.

## Knowledge profiles

- `src/analysis_ui/runtime/profiles.py`
  - added `data-model-attribute-extension-v1` as a source-backed multi-repository workspace;
  - added `system-interactions-v1` as a source-backed multi-repository workspace;
  - scenario policy is declarative through `assistant_profile_id`;
  - Data Model Extension master selects only stable technical context (repositories + PDM); mutable attribute requests remain in chat.
- `src/analysis_ui/runtime/knowledge_contracts.py`
  - recognizes the Data Model Extension physical-model requirement.

## Frontend

- `frontend/src/services/types.ts`
  - synchronized source-mode and multi-repository contracts.
- `frontend/src/views/ProfileWizard.vue`
  - renders input controls by `source_mode` instead of inferring them from execution scope;
  - supports multiple source repositories for workspace products;
  - supports PDM selection for Data Model Extension;
  - does not collect the mutable list of attributes to add;
  - hides report generation for knowledge products without a report profile.

## Runtime contract bundle

Regenerated from the current producer baseline:

- Core 0.44.16;
- Runner 0.10.9;
- KLC 0.59.36.

Updated files under `src/analysis_ui/resources/runtime_contracts/` include current Core evidence, materialization and knowledge-product catalogs plus their fingerprints/hashes.

## Version/dependencies/tests

- version moved to `2.0.0a77` (`2.0.0-alpha.77` in frontend package metadata);
- `pyproject.toml` now requires the canonical `knowledge-assistant>=0.20.0,<0.21.0` baseline;
- OpenAPI regenerated;
- source manifest regenerated;
- tests updated for source modes, multi-repository workspaces, reusable profiles and current runtime-contract versions.

No Core, Runner, KLC, API, Reporting, Assistant producer/consumer code was changed as part of this UI release.
