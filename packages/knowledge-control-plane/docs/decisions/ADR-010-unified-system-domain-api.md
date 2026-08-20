# ADR-010: fold data-model access into the unified system domain API

## Status

Accepted for `knowledge-control-plane 2.0.0a8`.

## Context

The previous checkpoint mounted a second FastAPI application to preserve a historical data-model contract. That required a second dependency, separate registry configuration, route-set validation, version probing, error translation and a second frontend client.

## Decision

Remove the separately mounted application and its public contract. Move the reusable Knowledge Layer query adapter into `knowledge-control-plane` and expose its results through versioned `systems` resources.

A system revision references:

- the source job;
- one Knowledge Layer artifact;
- an optional Markdown report artifact.

The latest successful publication becomes the active revision. Query endpoints may explicitly select an older revision.

## Consequences

- one FastAPI application and one OpenAPI document;
- one error model and one frontend client;
- no external systems registry or report path configuration;
- direct provenance from system to revision, job and artifacts;
- the former response content remains available under clearer paths;
- old URLs and `data_model_api/v1` are intentionally not retained.
