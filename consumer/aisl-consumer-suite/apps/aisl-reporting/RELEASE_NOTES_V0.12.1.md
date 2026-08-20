# aisl-reporting 0.12.1

## Fixed

- Attribute journeys can no longer be silently omitted by the renderer when the dataset selected them.
- Render validation records a warning for every missing selected `wire_path`; report generation always completes.
- The prompt requires one explicit card per selected journey and preserves the exact technical path in backticks.

## Removed

- Repository islands were removed from the workspace-interaction dataset, prompt, technical appendix and coverage. No legacy fields or dual-write remain.

## Unchanged

- Data-model and other report profiles are not modified.
## Validation behaviour

- Rendered Markdown is never rejected by content validation.
- Missing sections, missing attribute journeys and unknown evidence citations are recorded only as warnings.
- The `--strict-validation` CLI mode was removed. Dataset/schema validation before rendering remains strict.

