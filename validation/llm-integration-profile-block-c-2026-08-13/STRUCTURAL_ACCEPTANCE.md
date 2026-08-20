# Block C Structural Acceptance

## Results

- Real recorded UCP + SQL + PDM publication metadata: 44 capabilities, 16 exported HTTP tools.
- Narrow interaction/system-description revision: 5 capabilities, 16 interaction/system-description tools, 0 SQL/PDM tools.
- Every exported HTTP tool has a declarative API binding and pinned revision binding.
- Canonical binding ↔ Knowledge API OpenAPI parity: 52/52 tools PASS.
- `get_knowledge_context` is not exported as an HTTP tool; its revision/capability/artifact scope is embedded directly in the Integration Profile.
- Same UCP revision + same profile exported twice: canonical profile byte-identical; all rendered views identical.
- Capability change: tool set and integration profile fingerprint change.
- Live HTTP smoke: Consumer Kit generated without Knowledge Assistant; stdlib-only external consumer invoked Knowledge API directly from the kit and received observed evidence. PASS.

## Provenance caveat

The historical UCP+SQL+PDM materialization database from the earlier real acceptance was not retained in the current workspace. Therefore the UCP structural-profile acceptance uses its recorded immutable real execution metadata (capabilities/artifact descriptors) to generate the Consumer Kit. A separate live typed DuckDB fixture proves the actual publish/serve/direct-HTTP execution boundary. No claim is made that the historical UCP database itself was queried in this Block C run.

## Not evaluated

- Quality of a particular external LLM's natural-language answer or generated SQL.
- GroundedAssistant migration to consume the public Integration Profile (reserved for Block D).
- Full regression suite.
