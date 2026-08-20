# Test status — knowledge-layer-core 0.59.21

## Executed

- targeted contract/semantic tests: PASS (`14 passed` before packaging)
- real generic runtime gate on full `datamart_profile_fl` SQL knowledge + real TSA model-storage: PASS
- real `epk_client` acceptance at this step:
  - `epk_id`: 2 resolved value origins (`Individual.id`, base/history), no target-specific semantic gaps;
  - `last_name`: 2 resolved value origins (`IndividualName.surname`, base/history);
  - `active_flag`: 2 resolved value origins (`Individual.endDate`, base/history);
  - `row_actual_from/to`: still explicit upstream lineage gaps; next step.

Packaging regression and compile status are refreshed before ZIP publication.

## Packaging regression

- `python -m compileall -q knowledge_layer_core tests` — PASS
- targeted regression (`sql_target_source_mapping_semantics`, producer traversal, cross-artifact producer regression, materialization contracts/runtime) — PASS: 21 passed
- `SOURCE_MANIFEST_SHA256.json` validation — PASS
- release ZIP integrity (`unzip -t`) — PASS
