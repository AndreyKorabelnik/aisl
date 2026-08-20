# knowledge-layer-core 0.59.23

## Change

Makes schema-placeholder handling explicit on the product S2T value-source surface.

- ultimate SQL lineage continues to preserve the observed relation identity in the raw mapping;
- product value-source relations are resolved only from an exact observed `(workflow context, SQL file, placeholder)` binding;
- a binding is substituted only when its status is `resolved` and the resolved value contains no remaining placeholders;
- partial/template/missing bindings never fall back to guessed environment values; the original placeholder is preserved, `mapping_status` becomes `partial`, and `source_relation_placeholder_unresolved` is emitted with binding evidence;
- producer traversal now carries the terminal workflow context needed for context-safe placeholder resolution.

## Real `epk_client` validation

On the full real `datamart_profile_fl` SQL knowledge + real TSA model-storage:

- generic `sql-target-source-mapping` completed successfully;
- `epk_id`, `last_name`, and `active_flag` retained their correct current/history value origins;
- `${snp_src_schema_name}` is known only as `${inventory.cod_src_schema}` with partial/template evidence, while `${hist_src_schema_name}` has no complete observed binding in the current artifact;
- therefore neither placeholder is replaced with a guessed physical schema; affected product mappings are explicitly `partial` with diagnostics.

Target identifier display spelling is intentionally not inferred here. The real PDM already contains the canonical display codes and will be used by the thin Knowledge API projection layer without affecting lineage.
