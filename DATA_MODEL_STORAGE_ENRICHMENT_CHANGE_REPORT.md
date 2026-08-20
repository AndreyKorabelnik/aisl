# Data Model Storage Enrichment — Change Report

Date: 2026-08-17
Status: DATA_MODEL_STORAGE_ENRICHMENT_E2E_COMPLETE

## Goal

Finish the production path behind the existing deterministic `get_data_model_object_context` read tool so generic `build-data-model-v1` can publish already-existing storage knowledge when it is available, without making storage knowledge mandatory and without moving semantics into the API.

## Changes

### static-analysis-runner 0.10.28

- adds generic `optional_internal_materializations` to the existing Knowledge Product Catalog contract;
- `code-declared-data-model` declares existing `logical-storage-mapping` as optional enrichment;
- the canonical resolver follows the already-owned KLC dependency chain `logical-storage-mapping -> model-storage-semantics`;
- optional internal materializations retain required/optional provenance and are activated only for explicitly requested knowledge with optional sources enabled;
- missing/unregistered optional runtime/input yields a visible informational diagnostic and does not block the requested product;
- no fallback artifact or guessed storage meaning is produced.

### knowledge-control-plane 1.2.0a31

- repins the generated Runner knowledge catalog/bundle to Runner 0.10.28;
- KCP remains orchestration-only; no KCP storage resolver/materializer was introduced.

## Intentionally unchanged

- Core 0.44.23a7 and its evidence/stage catalog;
- KLC 0.61.0a38 materialization semantics;
- Prepared Knowledge Runtime 0.1.0.post13 read semantics;
- Knowledge API 0.38.0 and `data_model_object_context/v1` read projection;
- Knowledge Integration 0.1.16 Consumer Kit contract;
- Reporting and AISL Contract;
- no new concept, analyzer, materializer, compatibility adapter, dual-read/write or LLM-in-API path.
