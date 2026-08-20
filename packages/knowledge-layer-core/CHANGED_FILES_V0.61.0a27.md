# Changed files — Knowledge Layer Core 0.61.0a27

- `knowledge_layer_core/materialization_contracts.py` — materialization contracts now distinguish guaranteed `capabilities` from evidence-dependent `conditional_capabilities`; Repository Inventory declares structural-member capability as conditional.
- `knowledge_layer_core/materialization_runtime.py` — runtime validates actually published capabilities against the union of guaranteed and declared conditional capabilities without manufacturing missing capabilities.
- tests — Repository Inventory and contract/runtime regression coverage.
- version metadata — 0.61.0a27.
