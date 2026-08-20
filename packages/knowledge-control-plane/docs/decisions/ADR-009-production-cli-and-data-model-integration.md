# ADR-009: Real CLI contracts and the public data-model application are integrated explicitly

## Status

Superseded by ADR-010 for `knowledge-control-plane 2.0.0a8`. Retained as historical context.


## Context

CLI doubles validated orchestration flow but did not expose several details of the real runtime contract: repository materialization requires task/profile identifiers, profile IDs are not always canonical task IDs, output directories contain multiple manifest files, and `knowledge-api` must actually be present for the promised data-model routes to work.

Running orchestration and data-model HTTP endpoints as unrelated local servers would also complicate the single-process desktop/developer deployment targeted by `knowledge-control-plane serve`.

## Decision

1. `CommandBuilder` follows the public CLI contracts of the pinned supported versions and emits explicit task/profile identifiers.
2. Profile IDs are translated to canonical task IDs in one deterministic mapping function.
3. Retry selects canonical top-level manifests by priority and never relies on arbitrary recursive filename order.
4. A data-model pipeline validates that the resulting Knowledge Layer exposes the expected `common.data-model` capability and is not suite-only.
5. Reporting parameters supplied to `full_pipeline` are forwarded to the real reporting CLI.
6. `knowledge-control-plane serve` attaches only the five preserved routes from the FastAPI application returned by the public `knowledge_api.create_app()` factory. It does not import or call internal knowledge-api services.
7. Route attachment is fail-fast: a supported knowledge-api installation with a different public route set causes startup failure rather than silently exposing an incomplete API.

## Consequences

- integration tests with doubles remain fast, while a documented real-component smoke test is required before release checkpoints;
- orchestration cannot report success for an empty or wrong-profile data-model Knowledge Layer;
- generic and data-model endpoints share one process and one OpenAPI document without generic routes reimplementing data-model logic;
- `knowledge-api==0.2.2` is an explicit runtime dependency of this checkpoint;
- `field-catalog`, not a nonexistent list-tables endpoint, is the canonical catalog operation.
