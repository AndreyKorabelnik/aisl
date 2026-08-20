# Knowledge API 0.22.0 — test status

## Scope

System Interactions prepared-knowledge read surface over existing KLC read contracts.

## Results

- Full pytest suite: **65 passed**.
- `python -m compileall -q knowledge_api`: **passed**.
- Public OpenAPI regenerated and strict route inventory test: **passed**.
- System Interactions API tests cover:
  - interaction summary;
  - repository boundaries;
  - multiple execution contexts for one boundary interaction;
  - field contracts from their own capability/artifact;
  - diagnostics;
  - optional repository coverage from its own capability/artifact;
  - explicit `409 knowledge_artifact_unavailable` when optional knowledge is not published.
- No fallback from field-contract/coverage endpoints to `system-interactions` artifact.

## Known limitations at this checkpoint

- Real four-application System Interactions production/consumer E2E is the next validation step and is not claimed here.
- Coverage is exposed only when `workspace.repository-interaction-coverage` is actually published.
