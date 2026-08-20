# Test status — knowledge-layer-core 0.59.23

## Executed

- targeted regression (`producer traversal`, target-source semantics, SQL knowledge, cross-artifact mapping, materialization contracts/runtime): **PASS — 38 passed**;
- real generic runtime gate on full `datamart_profile_fl` SQL knowledge + real TSA model-storage: **PASS**;
- real `epk_client`: `epk_id`, `last_name`, `active_flag` retain expected current/history origins; schema placeholders are preserved and affected product mappings are `partial`;
- no Gold/environment schema values are used by runtime.

## Known limitation / next step

- target display spelling remains canonical/lower-cased in the KLC SQL surface; the real PDM provides observed display codes and the next step is a thin Knowledge API projection using that metadata.
- unresolved schema placeholders remain explicit until a complete workflow/environment binding is observed.

## Packaging checks

- `python -m compileall -q knowledge_layer_core tests` — PASS;
- `SOURCE_MANIFEST_SHA256.json` validation — PASS after regeneration;
- release ZIP integrity — PASS after packaging.
