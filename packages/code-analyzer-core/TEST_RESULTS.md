# Test results — code-analyzer-core 0.40.7

- Full module regression: **404 passed**.
- Focused constructor regression: **23 passed**.
- Real AT900 source validation:
  - constructor mappings: **259**;
  - constructor derivations: **453**;
  - production constructor gaps: **3**;
  - all three are intentional direct DAO-return gaps.
- Real UCP source validation:
  - `ucp_api`: **0** constructor gaps, **4** mappings, **2** derivations;
  - `ucp_tsa_v4`: **2** constructor gaps, **64** mappings, **714** derivations;
  - remaining unresolved expressions: `this.getLog()` and `supplier.get()`.
- Real AT900 full suite:
  - foundation, system-description and data-model: complete;
  - conceptual quality gate: passed;
  - DuckDB materialization: complete;
  - constructor-gap metric unchanged from 0.40.6: **3**.
- Real UCP canonical static data-model workspace:
  - repositories completed: **2/2**, failures: **0**;
  - DuckDB materialization: complete with `knowledge-layer-core 0.29.1`;
  - model objects with keys: **312**; key members: **514**;
  - relationships: **504**; excluded relationship candidates: **19**;
  - storage references: **224**; storage-key derivations: **202**;
  - reference-value/key correspondences: **241**;
  - all **224** storage references retain `physical_encoding=downstream_interpretation_required`.

No direct helper/DAO/framework return was converted into a mapping without an observed contract.
