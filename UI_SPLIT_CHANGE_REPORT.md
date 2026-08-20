# Analysis UI split — Knowledge Base Generator / Knowledge Chat

Date: 2026-08-14
Status: UI_SPLIT_COMPLETE

## Architecture

Framework-owned production product:
`Sources -> Knowledge Base Generator / Knowledge Control Plane -> Core -> Runner -> KLC -> Published Knowledge API revision`.

Consumer product handed off separately:
`Published Knowledge API revision -> knowledge-integration -> Knowledge Assistant -> Knowledge Chat`.

Knowledge Control Plane no longer contains or depends on Knowledge Assistant, chat sessions, conversations or chat frontend routes. Production terminates at published revision (plus optional report).

## Versions
- Knowledge Control Plane: 1.2.0a19
- Standalone Knowledge Chat: 0.1.0 (separate handoff artifact)
- Consumer-owned Knowledge Assistant: 0.25.1.post7
- Framework-owned knowledge-integration: 0.1.2

## Important boundary
- `knowledge-integration` remains framework-owned public consumer contract.
- `knowledge-assistant` is no longer a framework package.
- Chat must not depend on Core, Runner, KLC, source repositories or Generator runtime DB.
- Generator must not depend on LLM dialogue/session runtime.
- Published revision metadata may contain neutral `integration_profile_id` consumer guidance only.

## Final packaging hygiene
- removed a stale KCP lifecycle test call to the deleted Assistant-context store API;
- regenerated Knowledge Control Plane source manifest after the final split test change;
- corrected the unchanged `evidence-common` source manifest so it describes the actually packaged source tree rather than absent historical `.egg-info` files;
- no runtime semantics in `evidence-common` were changed.
