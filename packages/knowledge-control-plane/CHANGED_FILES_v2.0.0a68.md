# Analysis UI 2.0.0a68 — final E2E gap 1

- Added the explicit `code_analyzer_core` runtime command to the public configuration contract.
- Replaced the removed `static-analysis-runner physical-model` call with the canonical Core command:
  `code-analyzer-core analyze-physical-model <model> --artifact-output <dir>`.
- Added regression tests for the generated PDM command and default tool configuration.
- Synchronized backend and frontend package versions at 2.0.0a68 / 2.0.0-alpha.68.

No compatibility adapter or fallback was introduced.
