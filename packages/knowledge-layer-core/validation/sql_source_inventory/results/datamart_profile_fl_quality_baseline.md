# SQL Source Inventory Quality Report

- Fixture: `datamart_profile_fl-source-inventory-v1`
- Repository: `datamart_profile_fl`
- Target status: **failed**

## Metrics

| Metric | Value |
|---|---:|
| Relation precision | 1.0000 |
| Relation recall | 0.8957 |
| Classification accuracy | 1.0000 |
| Field precision | 1.0000 |
| Field recall | 1.0000 |
| Field-role accuracy | 1.0000 |
| Column resolution rate | 0.9391 |
| Cases passed | 28 / 30 |

## Target gates

| Gate | Target | Actual | Status |
|---|---:|---:|---|
| relation_precision | 0.9900 | 1.0000 | passed |
| relation_recall | 0.9800 | 0.8957 | failed |
| classification_accuracy | 0.9800 | 1.0000 | passed |
| field_precision | 0.9800 | 1.0000 | passed |
| field_recall | 0.9800 | 1.0000 | passed |
| field_role_accuracy | 0.9800 | 1.0000 | passed |

## Failed cases

### `hdfs/oozie-app/b2c_infra/__DATAMART_NAME__/wf/dml/epk_persdata_mapping/epk_persdata_mapping.sql`
- Missing relations: `custom_b2c_profile_fl.epk_client`, `custom_b2c_profile_fl.epk_client_doc`
- Unresolved column usages: 0 / 0

### `hdfs/oozie-app/b2c_infra/__DATAMART_NAME__/wf/dml/epk_client/epk_client.sql`
- Missing relations: `custom_b2c_profile_fl_stg.stg_epk_client_centaur_flag`, `custom_b2c_profile_fl_stg.stg_epk_client_currencyresident`, `custom_b2c_profile_fl_stg.stg_epk_client_deathinfo`, `custom_b2c_profile_fl_stg.stg_epk_client_distantmanager`, `custom_b2c_profile_fl_stg.stg_epk_client_docs`, `custom_b2c_profile_fl_stg.stg_epk_client_domain_client`, `custom_b2c_profile_fl_stg.stg_epk_client_literacy`, `custom_b2c_profile_fl_stg.stg_epk_client_relgroups`, `custom_b2c_profile_fl_stg.stg_epk_client_riskprofile`, `custom_b2c_profile_fl_stg.stg_epk_client_segment`, `custom_b2c_profile_fl_stg.stg_epk_client_selfempl`, `${snp_src_schema_name}.com_sbt_bm_ucp_common_model_dictionary_country`, `${snp_src_schema_name}.com_sbt_bm_ucp_common_model_dictionary_gendertype`, `${snp_src_schema_name}.com_sbt_bm_ucp_common_model_dictionary_partygroup`, `${snp_src_schema_name}.com_sbt_bm_ucp_common_model_dictionary_partystatustype`
- Unresolved column usages: 1 / 43
