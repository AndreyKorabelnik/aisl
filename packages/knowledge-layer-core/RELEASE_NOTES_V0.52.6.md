# knowledge-layer-core 0.52.6

Version 0.52.6 adds deterministic workflow-to-SQL context resolution on top of the canonical `sql_workflow_binding`, `sql_script_invocation`, SQL placeholder and repository-file facts.

## Added

- typed `sql_workflow_file_reference` table for exact repository-local file-reference candidates;
- typed `sql_workflow_context_file` table for transitive workflow/config-to-SQL reachability;
- typed `sql_placeholder_binding_resolution` table for context-scoped configuration bindings that reach SQL placeholders;
- capability `common.sql-workflow-context`;
- read-only queries:
  - `list_sql_workflow_context_files`;
  - `list_sql_placeholder_binding_resolutions`.

## Resolution boundary

- no global same-name substitution is performed;
- a binding reaches a SQL placeholder only through an observed workflow/config/script-invocation path;
- unresolved and ambiguous references remain explicit;
- when an observed source file already belongs to a concrete sibling directory such as `dml_inc` or `dml_arc`, exact source-directory context prevents a path from crossing into the other branch;
- an unresolved workflow branch variable still produces both probable branches rather than silently choosing one.

## Real repository result

The unchanged `datamart_profile_fl` SQL artifact was materialized successfully:

- 418 file-reference observations;
- 1,100 workflow-context paths;
- 248 context-scoped placeholder resolutions;
- 179 resolved, 13 ambiguous and 226 unresolved file references;
- 209 resolved, 9 probable and 30 partial placeholder resolutions.

For `b2c_profile_fl_epk_client_t0_individual.yaml`, the resolver reaches exactly two three-hop paths:

- `dml_inc/.../pipeline_epk_client_t0_individual.json` → `dml_inc/.../main_epk_client_t0_individual.sql` → `dml_inc/.../interim_epk_client_individual_stg.sql`;
- `dml_arc/.../pipeline_epk_client_t0_individual.json` → `dml_arc/.../main_epk_client_t0_individual.sql` → `dml_arc/.../interim_epk_client_individual_stg.sql`.

Both paths are `probable` because `$load_type` is not resolved in that workflow context. No mixed `inc → arc` or `arc → inc` path is published.
