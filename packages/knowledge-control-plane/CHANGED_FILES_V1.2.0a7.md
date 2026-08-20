# Changed files — Knowledge Control Plane 1.2.0a7

- `src/knowledge_control_plane/cli.py` — live stderr progress in JSON mode; one-shot runtime logging setup.
- `src/knowledge_control_plane/runtime/settings.py` — heartbeat setting and canonical per-job run-log path.
- `src/knowledge_control_plane/runtime/observability.py` — per-job human-readable log mirror.
- `src/knowledge_control_plane/runtime/one_shot.py` — run-log location announcement and silence heartbeat.
- `src/knowledge_control_plane/runtime/jobs.py` — duration/count/artifact-scan observability and resilient log mirroring.
- `tests/test_one_shot_observability.py` — observability contract tests.
- version metadata/tests — `1.2.0a7`.
