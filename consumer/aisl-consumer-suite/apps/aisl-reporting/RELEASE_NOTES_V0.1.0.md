# aisl-reporting 0.1.0

Date: 2026-08-17

First standalone release extracted from framework `knowledge-reporting 0.18.1`.

- Pure consumer of published Knowledge API/AISL revisions.
- Runtime inputs: Knowledge API URL, system id, optional revision id, report profile/presentation parameters.
- No Core, Runner, KLC, KCP or evidence-common runtime dependency.
- No direct local artifact fallback.
- OpenAI-compatible model renderer is implemented locally with `httpx`; deterministic `FileRenderer` remains available for tests/reproducible runs.
- Former direct `git-change-impact-report/v1` path is intentionally not included.
- Reports have their own lifecycle and do not mutate or republish AISL revisions.
