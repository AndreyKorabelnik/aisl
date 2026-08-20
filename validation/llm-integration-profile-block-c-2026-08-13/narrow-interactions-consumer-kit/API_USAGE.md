# Knowledge API usage

System: `narrow-interactions`  
Revision: `rev-narrow-interactions` (pinned)

For each tool use its `api_binding`. Replace `{system_id}` with the pinned system id. Inject the pinned revision exactly where `revision_binding` specifies. Map tool arguments according to `arguments`; `fixed_query` and `fixed_body` are mandatory constants. Never replace the pinned revision with active/latest during a session.
