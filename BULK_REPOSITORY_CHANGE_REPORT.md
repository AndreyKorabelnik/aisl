# Change Report — Bulk Repository Processing

Date: 2026-08-14

## Goal

Mass-process repositories without treating a project/portfolio as one multi-repository analysis scope. Each repository must use the existing repository-scoped production path and its checkout must be temporary.

## Implemented

### Runner 0.10.24

- Added generic `repository-batch-run` runtime and CLI.
- Added `repository-batch-discover` for Bitbucket Data Center project membership discovery without cloning.
- Reused the existing Bitbucket Data Center discovery/auth/pagination/clone implementation; no second SCM client was created.
- Extracted shared repository selection and Runner-owned temporary-run primitives from the special data-model discovery path.
- Existing `data-model-discovery` now reuses those primitives; its typed candidate workflow remains otherwise independent.
- A batch accepts only a repository-scoped `knowledge_profile/v2` and creates a separate profile scope (`scope_id=repo_id`), input inventory, execution plan and knowledge execution for every repository.
- Current execution is deliberately sequential: one checkout at most.
- Per-repository failures are explicit and processing continues with later repositories.
- Checkout and preparation directories are removed after every repository in `finally`; the whole temporary run root is removed at batch completion.
- Persistent `repository_batch_repository_result/v1` records durable repository URL/ref/resolved commit, status, diagnostics and prepared result reference.

### KLC 0.61.0a27 / Runner planning

A pre-existing single-repository Repository Inventory defect was found by the real batch smoke: `common.repository-structural-members` was declared as an unconditional KLC output although FI-001 intentionally publishes it only when optional structured-member evidence was evaluated.

Generic fix:
- KLC materialization contracts now distinguish guaranteed `capabilities` from `conditional_capabilities`.
- Repository Inventory declares `common.repository-structural-members` as conditional.
- KLC runtime accepts only guaranteed + explicitly declared conditional capabilities; it does not invent missing capabilities.
- Runner exposes conditional capabilities in the execution node for diagnostics but validates only guaranteed capabilities as hard expected outputs.

No Core change was required.

### Knowledge Control Plane 1.2.0a16

Pinned Core/KLC/Runner runtime catalogs were regenerated from canonical builders for Core `0.44.23a5`, KLC `0.61.0a27`, Runner `0.10.24`.

## Explicit non-goals

- no multi-repository Core/Runner scope;
- no KLC multi-repository assembly/materializer in this block;
- no Portfolio Inventory producer change;
- no Benchmark Miner work;
- no Task/Suite or parked portfolio-topology restoration;
- no compatibility adapter/dual-read/dual-write;
- no uncontrolled parallel cloning.
