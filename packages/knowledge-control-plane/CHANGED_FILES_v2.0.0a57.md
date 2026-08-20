# Changed files — Analysis UI 2.0.0a57

- `src/analysis_ui/api/generic_v1/models.py` — новый строгий контракт стадий и удаление общего искусственного процента.
- `src/analysis_ui/runtime/pipeline.py` — динамический план только из применимых стадий и пользовательские названия под мастера.
- `src/analysis_ui/runtime/jobs.py` — фактические переходы стадий по сообщениям Runner, измеримый Git checkout и подоперации отчёта.
- `frontend/src/components/ProgressTracker.vue` — динамическая шкала, неопределённый индикатор и текущая операция.
- `frontend/src/views/Analysis.vue` — передача фактических стадий задания.
- `frontend/src/store/analysis.ts`, `frontend/src/services/types.ts`, `frontend/src/services/api.ts` — новый frontend-контракт прогресса и обновление стадий по SSE.
- `frontend/src/components/TaskHistory.vue` — удалён фиктивный процент из истории.
- `frontend/src/components/AssistantContextRepositoryPreparation.vue` — удалён фиктивный процент из подготовки контекста.
- `scripts/verify_frontend_visual_baseline.py` и визуальный manifest — закреплён новый экран прогресса.
- `tests/test_dynamic_pipeline_progress.py`, `tests/test_frontend_dynamic_progress.py` и затронутые runtime/publication tests — регрессия нового контракта.
- version metadata, OpenAPI and release documentation — 2.0.0a57.
