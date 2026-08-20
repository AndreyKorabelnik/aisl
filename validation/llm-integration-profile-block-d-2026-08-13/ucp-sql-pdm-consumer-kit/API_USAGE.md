# Knowledge API usage

System: `ucp-sql-pdm`  
Revision: `rev-real-ucp-sql-pdm` (pinned)

For each tool use its `api_binding`. Replace `{system_id}` with the pinned system id. Inject the pinned revision exactly where `revision_binding` specifies. Map tool arguments according to `arguments`; `fixed_query` and `fixed_body` are mandatory constants. Never replace the pinned revision with active/latest during a session.
