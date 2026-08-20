# Knowledge API usage

System: `ucp-data-model-enriched`  
Revision: `rev-88415df4d14df2ff3827b01c` (pinned)

For each tool use its `api_binding`. Replace `{system_id}` with the pinned system id. Inject the pinned revision exactly where `revision_binding` specifies. Map tool arguments according to `arguments`; `fixed_query` and `fixed_body` are mandatory constants. Never replace the pinned revision with active/latest during a session.
