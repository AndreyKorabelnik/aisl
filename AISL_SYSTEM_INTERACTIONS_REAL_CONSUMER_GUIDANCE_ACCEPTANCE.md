# AISL System Interactions — real production + compact consumer guidance acceptance

Date: 2026-08-15  
Status: **SYSTEM_INTERACTIONS_AISL_REAL_CONSUMER_GUIDANCE_BLOCK_COMPLETE**

## What is proven

The current canonical System Interactions producer path was executed on four real repositories through the official stack:

`Core → Runner → KLC → knowledge_execution_result/v2 → Knowledge API publication → pinned AISL revision → consumer read`.

No new analyzer, second producer, second Knowledge Layer or compatibility read path was added.

Real KCP job: `job-7633eb94b1e546f6ae74dd250f80b821`  
Scenario: `analyze-system-interactions-v1`  
Published revision: `rev-29fbde443c7bd63854ac8b1e`  
Status: **succeeded**

Fresh producer result:

- 12 analyzer executions;
- 4 KLC materializations;
- 16 built producer nodes, 0 reused in this fresh run;
- 6 published KnowledgeProducts/capabilities surface entries;
- 3 matched `system_interaction` rows;
- 3 matched boundary interactions;
- 8 execution contexts;
- 46 field contracts;
- 17 explicit interaction diagnostics.

The three matched interactions are:

1. `sbpr-ucp-intergation → gateway-sberid-userinfo-by-ucpid`, `POST /sberProfileId/search`;
2. `sbpr-ucp-intergation → gw-sberid-update-phone-flags`, `POST /updatePhoneFlags`;
3. `sbpr-ucp-intergation → gw-sberprofile-create-update-extprofile`, `/ucp/updateOrCreate → /updateOrCreate`.

All three remain **probable**. This is intentional: the producer does not have addressing evidence strong enough to promote them to confirmed. The consumer change does not alter that classification.

`/giveSberProfileId` remains unmatched and visible through diagnostics; no false interaction was created.

## Proven consumer friction

Before this block, `system-interactions/v1` exposed the high-level interaction list but no exact compact read for a selected matched interaction. The recommended follow-up surface forced the agent toward separate repository-boundary inventory / execution-context / field-contract reads. The raw canonical rows also contain large repeated `payload_json` evidence structures.

The fix is consumer-only:

`list_system_interactions → get_system_interaction_context`

New Knowledge API read:

`GET /api/knowledge/v1/systems/{system_id}/interactions/{interaction_id}/guidance`

It groups only by exact already-published `interaction_id` and `boundary_interaction_id`, surfaces KLC-owned endpoint/match/confidence/basis plus bounded contexts/contracts, and performs **no semantic derivation**.

## Real payload effect

Raw detail = exact matched boundary pair + execution contexts + field contracts for the same interaction.

| Interaction | Target | confidence | Raw detail bytes | Compact guidance bytes | Reduction | Field contracts total / presented |
|---|---|---|---:|---:|---:|---:|
| `/sberProfileId/search` → `/sberProfileId/search` | `gateway-sberid-userinfo-by-ucpid` | probable | 157 728 | 8 448 | **-94.6%** | 2 / 2 |
| `/updatePhoneFlags` → `/updatePhoneFlags` | `gw-sberid-update-phone-flags` | probable | 71 917 | 11 397 | **-84.2%** | 7 / 7 |
| `/ucp/updateOrCreate` → `/updateOrCreate` | `gw-sberprofile-create-update-extprofile` | probable | 1 028 267 | 47 879 | **-95.3%** | 37 / 20 |

For update/create the default projection reports `37 total / 20 presented / truncated=true`; truncation is not interpreted as absence. Canonical detailed endpoints remain available for continuation.

## Consumer profile

`system-interactions/v1` retrieval policy is now profile **v2**.

- before: 7 tools;
- after: 8 tools;
- added: `get_system_interaction_context`;
- argument surface: only `interaction_id`;
- limits are deterministic binding defaults: `context_limit=8`, `field_limit=20`;
- revision binding remains **pinned** to `rev-29fbde443c7bd63854ac8b1e` in the real acceptance.

`list_interaction_boundaries` remains repository-boundary inventory; it is no longer presented as the normal way to reconstruct an already-published matched interaction.

## Tests

- Knowledge API 0.30.13: **99/99 PASS**, complete split runs `45/45 + 54/54`.
- Knowledge Integration 0.1.12: **16/16 PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED**.
- Knowledge Control Plane 1.2.0a22: **94/94 PASS** in a clean environment.
- Real four-repository KCP → Runner → KLC → publication: **PASS**.
- Live Knowledge API read on the published revision with the new guidance endpoint: **PASS**.

A monolithic Knowledge API test invocation timed out late without reporting failures and is **not** counted as PASS; the complete split runs above are authoritative.

An initial broad KCP test invocation inherited real-run environment overrides and produced 92 PASS / 2 environment-dependent failures. A clean-environment rerun produced 94/94 PASS; no KCP code change was made.

## Limits / unresolved

- A real external LLM behavioral trace was not executed. Deterministic Consumer Kit + exact read behavior is proven; model behavior remains an external acceptance item.
- Historical Manual Gold contains deeper field-path cases (for example collection/lambda propagation and ingress-controller → service field projection). This block does not claim those unrelated Core path gaps are fixed merely because interaction-level materialization is healthy.
- The historical composed attribute revision `rev-1fed54320afb0632c144e098` is recorded in recovery metadata, but its live base publication/catalog is not packaged here. It is also a different system identity from the current interaction workspace. No synthetic or automatic cross-system snapshot merge was attempted.

## Architectural conclusion

**System Interactions does not require a new producer or Core change.** The existing observed evidence + KLC mechanism reproduces the real interaction structure on the current canonical stack. The proven gap was consumer ergonomics, and it is fixed at the thin read/integration boundary without moving semantics out of KLC.
