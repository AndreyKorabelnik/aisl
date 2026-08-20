# Test status — knowledge-layer-core 0.59.12

- Targeted/contract tests (`test_cross_artifact_data_model_mapping.py`, `test_sql_analysis_knowledge_layer.py`, `test_materialization_contracts.py`): **25 passed**.
- `compileall` for `knowledge_layer_core`: **OK**.
- Fresh real four-input cross-artifact validation:
  - script materializations: **235**;
  - end-to-end evidence paths: **334**;
  - unique logical-field→target-column correspondences: **212**;
  - logical fields represented: **94**;
  - target PDM columns represented: **138** across **10** tables;
  - `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number`: **2 evidence-backed paths** (current + history).
- Known next Gold gap: `BirthPlace.value → epk_client.birth_place` has no composed end-to-end path because the specialized preparation chain is not currently reachable through the workflow graph.
