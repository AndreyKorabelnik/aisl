# Test status — knowledge-api 0.19.0

- `python -m compileall -q knowledge_api`: PASS.
- data-model + SQL API targeted suite: 13 passed.
- API/OpenAPI contract suite: 14 passed.
- real HTTP publication + S2T query: PASS (200, 90 mappings in one default call).
- real detailed `/data-model/lineage` smoke: PASS.
- real HTTP Gold diagnostic: 113/132 exact target+table+column matches ignoring schema; same as KLC.
