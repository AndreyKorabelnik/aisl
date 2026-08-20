# aisl-workbench 0.4.0 — Build shell

- Renamed user-facing shell to **AISL Platform** while keeping the independent `aisl-workbench` package name.
- Added Build tab over the public Knowledge Control Plane `/api/v1` contract.
- Scenario/source-mode/declared scenario parameters are discovered dynamically from KCP.
- Supports repository, multi-repository and knowledge-revision source modes.
- Added local repository discovery through KCP.
- Added production preview, run, recent jobs, job status and publication handoff.
- Successful publication can be opened as the exact immutable revision in the existing consumer views.
- Added a deliberately narrow KCP proxy; configuration/admin writes are not exposed.
- Knowledge API proxy remains read-only.
- No Core/Runner/KLC orchestration semantics were copied into the UI.
