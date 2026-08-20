# Change Report — Bulk Repository High-Level CLI

Date: 2026-08-14
Status: COMPLETE

## Goal

Expose the already-completed Runner repository-batch runtime through the existing user-facing `knowledge-control-plane run` command. A normal user must not create `knowledge_profile/v2` JSON or pass Core/Runner/KLC catalog paths.

## Implemented

Knowledge Control Plane `1.2.0a17` now accepts `--bitbucket-project-url` on the existing `run` command.

For batch execution Control Plane:
1. resolves the selected Analysis Scenario from the official scenario registry;
2. requires `source_mode=repository` and a repository-scoped Knowledge Profile;
3. serializes that official profile into a temporary `knowledge_profile/v2`;
4. resolves the packaged/pinned Core evidence, Knowledge and KLC materialization catalogs;
5. calls the existing Runner `repository-batch-run` command;
6. lets Runner own Bitbucket discovery, temporary checkout, independent per-repository Core/KLC execution, diagnostics and cleanup;
7. removes the temporary Control-Plane profile automatically.

No new analyzer, producer, materializer, SCM client, clone path or execution engine was added.

## Normal CLI

```bash
export BITBUCKET_TOKEN='...'
knowledge-control-plane run \
  --scenario build-repository-inventory-v1 \
  --bitbucket-project-url 'https://bitbucket.example/projects/ABC'
```

For first live acceptance:

```bash
knowledge-control-plane run \
  --scenario build-repository-inventory-v1 \
  --bitbucket-project-url 'https://bitbucket.example/projects/ABC' \
  --repository-limit 3
```

`--output` is optional. If omitted, Control Plane creates a timestamped directory under its configured analysis output root.

## Semantics

This remains bulk orchestration of independent repositories. It does not create a multi-repository Core/Runner scope and does not perform KLC portfolio assembly.

The batch path currently persists independent Runner/KLC repository results and the batch manifest. It does not silently publish a combined Knowledge API/portfolio revision.

## Explicit diagnostics

Options that have no defined batch meaning (`--system-id`, `--physical-model`, `--report`, `--display-name`, custom audience/detail/focus/parameters, knowledge revisions) are rejected rather than silently ignored.

Scenarios requiring additional mandatory external inputs are rejected before Runner is invoked.
