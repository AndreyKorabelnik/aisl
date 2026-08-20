# Test status — knowledge-control-plane 1.2.0a22

Date: 2026-08-15

## PASS

- Focused subprocess regression: direct child exits while descendant retains inherited stdout/stderr; executor returns without waiting for descendant lifetime and emits an explicit diagnostic warning.
- Timeout regression: owned process group is terminated and timeout remains explicit.
- Targeted affected KCP suite: 54 PASS.
- Full KCP suite with canonical source paths: 94 PASS.
- Real UCP + TSA + PDM one-shot: PASS.
  - job: `job-a81b0391ddc944a08fac298a47781934`;
  - terminal persisted status: `succeeded`;
  - Runner stage: 48.1 s;
  - post-Runner artifact scan: 47 registered artifacts in 0.3 s;
  - publication: 0.3 s;
  - total job duration: 52.7 s;
  - published revision: `rev-07ee3380d57d95910de989c9`;
  - 5 KnowledgeProducts / 17 capabilities visible through Knowledge API.

## Environment note

An earlier full-suite invocation produced 93 PASS / 1 FAIL because the source-tree `PYTHONPATH` incorrectly pointed at `static-analysis-runner/src`; this package is rooted at `static-analysis-runner/`. The isolated failing test passed once the canonical package root was used, and the corrected full-suite run is 94/94 PASS. The environment-only run is not counted as a framework failure or a PASS.

## Scope

No full framework regression was required because production semantics outside KCP were not modified. Real multi-product producer/publication acceptance exercises the affected end-to-end lifecycle.
