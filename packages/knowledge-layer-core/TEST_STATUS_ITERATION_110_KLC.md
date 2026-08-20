# Iteration 110 KLC test status

- Focused SQL target/workflow/insertion regression: 5 passed, 12 deselected.
- Additional initial focused run: 6 passed, 11 deselected.
- `compileall knowledge_layer_core`: passed.
- Real datamart smoke: `epk_client` resolved to `custom_b2c_profile_fl.epk_client`; insertion resolver selected `stg_epk_client_birthplace_snp.sql`.
- Full KLC suite was not run because schema, ingestion and materialization were unchanged.
