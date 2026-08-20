# knowledge-api 0.19.1 — product S2T artifact routing

## Change

`GET /api/knowledge/v1/systems/{system_id}/sql/target-column-lineage` now reads the dedicated `sql-target-source-mapping/v1` artifact and capability `common.sql-target-value-source-mapping`.

The API performs no producer traversal, SQL interpretation, parent-key inference, placeholder resolution, or Gold-driven mapping. It only groups the KLC product value-source rows by target column, preserves gap-only targets, and projects KLC diagnostics.

If a unique physical-model table for the requested target is published in the same revision, its exact column codes are used only for target display spelling (for example `confirmedByOperator`, `riskProfile`, `investingHorizon`, `pon_managerCode`). Missing or ambiguous PDM metadata never changes lineage identity and is not guessed.

The detailed `/data-model/lineage` endpoint remains backed by cross-artifact data-model knowledge.

## Real epk_client gate

- HTTP 200 on final KLC 0.59.26 S2T artifact.
- 93 target entries: 86 with proven value sources and 7 gap-only/unresolved targets.
- `epk_id`: exactly two current/history `Individual.id` sources.
- `client_centaur_flag`: two proven UNION sources.
- unresolved schema placeholders remain verbatim and keep mappings partial.
