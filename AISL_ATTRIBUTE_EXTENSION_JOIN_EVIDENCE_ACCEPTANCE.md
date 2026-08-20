# AISL attribute-extension JOIN evidence — real acceptance

Date: 2026-08-15  
Status: **PASS with explicit residual source-column check**

## Real inputs

- UCP code model: `ucp-api`;
- UCP TSA storage conversion: `ucp-tsa-v4`;
- datamart SQL: `datamart_profile_fl`;
- B2C physical model: `CDO_B2C_PDM - ag 20260710.pdm`.

Official user-facing Knowledge Product: `data-model-attribute-extension`.
Runner automatically resolved its internal producer/materialization dependencies; no scenario-specific second execution path was created.

Post-fix execution:

- schema: `knowledge_execution_result/v2`;
- result fingerprint: `883c28b2afe3fc8a0f8d595d48bec23a552072c2383ef178552b08cba27cd626`;
- status: `completed`;
- KnowledgeProducts: 8;
- published capabilities: 44.

Published consumer revision:

- system: `aisl-attribute-extension-real`;
- revision: `rev-cfb071123bdb5e8b54eb06a1`;
- profile: `attribute-addition-plan/v1`, profile version 11;
- consumer-kit fingerprint: `776dadab53139e9e5ad134d16e1164bacef9813d3f117ab19785d27da56a8e25`;
- capability-gated tools: 17.

## Business request

Representative request: **«название региона рождения клиента»**.

AISL exposes two different observed domain meanings and therefore should not silently merge them:

1. `BirthPlace.region` — `String`, documentation **«Регион (историческое название)»**;
2. `BirthPlace.regionCode → Region.name` — `regionCode` is a reference to dictionary `Region`, while `Region.name` is **«Наименование»**.

For the wording «название региона» the dictionary path is a strongly supported preferred interpretation; the historical direct string remains a visible alternative.

## Observed / confirmed technical evidence

For `BirthPlace.regionCode → Region`:

- declared relationship is observed;
- `join_method=resolve_reference_value_to_target_key`;
- relationship/storage encoding confidence: `confirmed`;
- SQL generation status: `transformation_required`;
- target storage key field: `key`;
- exact structural correspondence exists between source reference encoding and target key construction;
- three typed storage observations explicitly record `referenceField("regionCode", ...)` with source provenance;
- representative expressions include `"Region_" + birthPlace.getRegionCode().getCode()` and matching target key construction `"Region_" + region.getCode()`.

The target dictionary `Region` and its key/name fields are observed in SQL.

## SQL evidence boundary

Current BirthPlace staging source reads the source relation with `SELECT *`, but no explicit SQL usage of BirthPlace `regionCode` is observed.

The current product therefore correctly publishes:

- `source_relationship_field_observed_in_sql=false`;
- `exact_relationship_sql_join_observed=false`;
- `source_storage_field_observation_count=3`;
- diagnostic `storage_reference_field_not_observed_in_current_sql`.

Four real SQL JOIN examples remain useful but are now labeled as analogs rather than exact evidence:

- 3 × `target_key_analog`;
- 1 × `target_relation_analog`.

Examples include observed patterns such as:

```sql
SUBSTRING_INDEX(addr.regioncode, ':', -1) = cmd_region.key
```

and

```sql
r.key = SPLIT(pn.region, ':')[1]
```

These support the encoding/JOIN pattern, but they do not prove an existing exact BirthPlace.regionCode JOIN.

## Target and insertion context

Consumer-only Knowledge API reads on the pinned revision returned:

- target `custom_b2c_profile_fl.epk_client` ranked #1, score 154;
- insertion workflow `.../wf/dml/epk_client/stg_epk_client_birthplace_snp.sql`, score 177;
- propagation status `resolved`;
- PDM target `epk_client / Клиент ФЛ`, 91 columns, 1 key, 12 outbound relationships.

## Useful answer classification

A consumer can now propose a JOIN such as:

```sql
LEFT JOIN ${snp_src_schema_name}.com_sbt_bm_ucp_common_model_dictionary_region birth_region
  ON birth_region.key = SPLIT(source.regioncode, ':')[1]
```

with projection:

```sql
birth_region.name AS birth_region_name
```

Classification: **strongly_supported inference / proposed SQL**, not confirmed current SQL.

Basis:

- confirmed declared relationship;
- confirmed storage reference/key encoding;
- observed storage field `regionCode` with provenance;
- observed Region dictionary/key/name usage;
- observed analogous JOIN patterns;
- resolved target/insertion workflow.

Residual gap: confirm that the raw BirthPlace source exposed to this staging SQL actually provides the column under the SQL name `regioncode` (or determine its real SQL column name). The absence of this observation is visible and does not erase the otherwise useful proposal.

## Acceptance conclusion

The scenario demonstrates the intended framework behavior: do not require mathematical proof before giving useful information, but preserve the line between observed exact evidence and a strongly supported proposal. No new AISL architecture mechanism was required.
