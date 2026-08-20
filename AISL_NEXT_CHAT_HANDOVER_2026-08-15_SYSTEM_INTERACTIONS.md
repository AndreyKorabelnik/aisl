# AISL / Auto-analysis next-chat handover

Date: 2026-08-15  
Status: **SYSTEM_INTERACTIONS_AISL_REAL_CONSUMER_GUIDANCE_BLOCK_COMPLETE**

Start from the canonical ZIP and recovery SHA supplied with this release; verify checksums before editing.

## Current architecture status

AISL Core Architecture is formed. System Interactions has now been revalidated on the current canonical producer stack and exposed through a compact revision-pinned consumer read.

The real acceptance used four repositories:

- `sbpr-ucp-intergation`;
- `gateway-sberid-userinfo-by-ucpid`;
- `gw-sberid-update-phone-flags`;
- `gw-sberprofile-create-update-extprofile`.

Real publication:

- system: `ucp-system-interactions`;
- revision: `rev-29fbde443c7bd63854ac8b1e`;
- interactions: 3;
- execution contexts: 8;
- field contracts: 46;
- diagnostics: 17.

Do not change Core for this domain without new evidence of a missing observed fact. Current producer acceptance is healthy.

## Consumer change

Knowledge API 0.30.13 + Knowledge Integration 0.1.12 add a compact exact System Interactions read:

`list_system_interactions → get_system_interaction_context`

Profile: `system-interactions/v1`, version 2, tool catalog version 5.

The projection performs no matching/inference. It preserves KLC confidence/basis and makes truncation explicit.

## Tests

- Knowledge API: 99/99 PASS (45 + 54 split).
- Knowledge Integration: 16/16 PASS.
- KLC: 252 PASS, 8 SKIPPED.
- KCP: 94/94 PASS in clean environment.
- Real four-repository KCP/Runner/KLC/publication/read: PASS.

## Important unresolved / do not fake

- External LLM behavioral trace remains not run.
- Do not automatically merge `ucp-system-interactions` with historical `ucp-data-model` / attribute revisions. The current recovery does not carry the live base publication/catalog and system identity differs. Cross-system dependencies remain provenance unless an explicit product/system ownership decision says otherwise.
- Historical collection/lambda and ingress-controller→service field-path gaps are not declared fixed by this block.

## Recommended next product block

Proceed to **Reference Data / НСИ through AISL** using the same cycle:

Manual Gold → current prepared knowledge → structural diff → generic fix only if proven → typed KnowledgeProduct → official publication → one pinned revision → consumer exact/compact read.

First inspect reuse of the existing `reference-data` materialization/read before adding any producer.

Parked scope stays parked: UCP 91 blind external run, FI-002, vector/embedding retrieval, portfolio topology, universal graph, agent memory/planning, compatibility cleanup without a proven duplicate.
