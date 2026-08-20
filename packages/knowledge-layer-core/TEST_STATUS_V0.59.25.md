# Test status — knowledge-layer-core 0.59.25

- targeted S2T/materialization/query regression: **18 passed**;
- real `datamart_profile_fl` generic materialization: PASS;
- real `epk_client` result: `hash_val` / `row_hash` are no longer value-source rows and have explicit `ultimate_source_identity_unresolved` gaps; `epk_id`, `last_name`, `active_flag`, `row_actual_from`, `row_actual_to` retain the 0.59.24 value-source results;
- compileall: PASS;
- source manifest validation: PASS;
- ZIP integrity: PASS (current module package / bundle gate).
