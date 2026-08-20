# Test status — knowledge-layer-core 0.59.22

## Executed

- targeted regression (`sql producer traversal`, `sql target-source semantics`, SQL knowledge, cross-artifact mapping, materialization contracts/runtime): **PASS — 36 passed**;
- real generic runtime gate on full `datamart_profile_fl` SQL knowledge + real TSA model-storage: **PASS**, completed in ~15.8 s;
- real `epk_client` acceptance:
  - `epk_id`: 2 resolved value origins (`Individual.id`, base/history), target gaps 0;
  - `last_name`: 2 resolved `IndividualName.surname` origins;
  - `active_flag`: 2 resolved `Individual.endDate` origins;
  - `row_actual_from` / `row_actual_to`: local lineage gaps removed, window control usages excluded, 0 staging relations exposed as product value sources;
  - unresolved intermediate frontiers are explicit `intermediate_producer_unresolved` diagnostics rather than false ultimate sources.

## Known limitation / next investigation

- the real SQL proves broader validity-boundary dependencies for `row_actual_from/to` than the manual Gold (52 external origins per field, plus unresolved intermediate producer frontiers). No Gold-driven collapse is applied; this is retained for explicit semantic/evidence comparison.
- schema placeholders and user-facing identifier spelling are the next block.

## Packaging checks

- `python -m compileall -q knowledge_layer_core tests` — PASS;
- `SOURCE_MANIFEST_SHA256.json` validation — PASS after regeneration;
- release ZIP integrity (`unzip -t`) — PASS after packaging.
