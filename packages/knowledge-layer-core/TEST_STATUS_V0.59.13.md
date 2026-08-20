# Test status — knowledge-layer-core 0.59.13

- Targeted/contract tests: **25 passed**.
- `compileall` for `knowledge_layer_core`: **OK**.
- Real four-input cross-artifact validation:
  - workflow dependencies: **24** total = **21 matched/derived + 3 candidate/ambiguous**;
  - script materializations: **396**;
  - end-to-end evidence paths: **946**;
  - unique logical-field→target-column correspondences: **551**;
  - cross-workflow evidence paths: **209**;
  - `BirthPlace.value → epk_client.birth_place`: **2** paths;
  - `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number`: **2** paths.
- Ambiguous workflow producers are retained as candidates and excluded from lineage traversal.
