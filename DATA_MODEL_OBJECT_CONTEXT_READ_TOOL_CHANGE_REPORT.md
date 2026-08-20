# Data Model Object Context Read Tool — Change Report

Date: 2026-08-17
Status: DATA_MODEL_OBJECT_CONTEXT_READ_TOOL_COMPLETE

## Goal

Expose a deterministic object-centric data-model read tool for external LLM/agent consumers. The Knowledge API performs no LLM reasoning.

## Changes

- Prepared Knowledge Runtime 0.1.0.post13:
  - exact read queries for existing `logical-storage-model-mapping` products;
  - exact read queries for existing `model-storage-semantics` products.
- Knowledge API 0.38.0:
  - new `data_model_object_context/v1` projection;
  - new GET `/api/knowledge/v1/systems/{system_id}/data-model/object-context/{object_id}`;
  - declared object/fields/relationships are always returned when the declared-model product is published;
  - storage mapping/derivations are added only when the corresponding existing products are members of the same selected revision;
  - absent optional storage knowledge is explicit `not_available`;
  - physical SQL/PDM join is never inferred by this projection.
- Knowledge Integration 0.1.16:
  - tool catalog v9;
  - `data-model/v1` resource version 2;
  - new `get_data_model_object_context` tool and API binding.

## Intentionally unchanged

- Core analyzers and evidence catalog.
- Runner execution planning.
- KLC materializers and knowledge semantics.
- Knowledge Control Plane `build-data-model-v1` composition.
- No new concept, analyzer, materializer, compatibility adapter, dual-read or LLM-in-API path.
