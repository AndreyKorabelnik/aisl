# Data Model Object Context Read Tool — Acceptance

Date: 2026-08-17

## Acceptance result

PASS for the implemented read boundary.

## Verified behavior

1. Declared-only revision
   - object context is available;
   - fields and declared relationships are returned;
   - missing storage products are surfaced as `storage_context.status = not_available`;
   - no storage or physical join is guessed.

2. Storage-enriched synthetic revision using existing products
   - exact logical-storage mapping is attached to the declared relationship;
   - published `mapping_status`, `mapping_basis`, `knowledge_class` and target alignment are preserved;
   - model-storage key/reference derivations are preserved;
   - physical SQL/PDM mapping remains explicitly `not_observed` because this read model does not consume physical join evidence.

3. Real UCP AISL revision
   - system: `ucp-data-model`;
   - revision: `rev-cf1820d42ff0cf021ccb358a`;
   - generated `data-model/v1` Consumer Kit exports five tools including `get_data_model_object_context`;
   - the existing revision is not modified or republished.

## Boundary

This acceptance does not claim that the current generic `build-data-model-v1` publishes model-storage semantics. It currently publishes declared-model knowledge only for the referenced UCP revision. The new read tool enriches only from products already published in the selected revision.
