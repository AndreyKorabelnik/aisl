# Changed files — analysis-ui 2.0.0a32

- `src/analysis_ui/runtime/profiles.py` — neutral built-in `knowledge-context-pipeline:v1`.
- `frontend/src/components/AssistantContextRepositoryPreparation.vue` — repository inputs, automatic profile selection, two knowledge-only jobs, progress restoration and artifact registration.
- `frontend/src/views/AssistantContexts.vue` — repository-analysis mode in the prepared-context wizard.
- `frontend/src/services/api.ts` — typed knowledge-context job creation and lightweight job polling.
- `frontend/src/services/types.ts` — repository preparation request contract.
- `tests/test_profile_discovery.py` — neutral pipeline contract regression.
- `tests/test_assistant_context_frontend.py` — repository wizard, no-report and reload-recovery regressions.
- OpenAPI, versions, release notes and source manifest synchronized.
