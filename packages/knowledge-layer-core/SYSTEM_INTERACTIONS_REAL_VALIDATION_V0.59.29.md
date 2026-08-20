# Real validation — system interactions — KLC 0.59.29

Workspace:
- `sbpr-ucp-intergation`
- `gateway-sberid-userinfo-by-ucpid`
- `gw-sberid-update-phone-flags`
- `gw-sberprofile-create-update-extprofile`

Baseline Core evidence: 0.44.16, reused unchanged.
Manual Gold: `system-interactions-manual-gold-1.0.0-2026-08-08.zip`, SHA-256 `c0e30808f0cc8ebcde87b60f70f4b98d8f20ce32e3f97b046cf0b8cd2ae37786`.

## Before -> after

- `repository_interaction_boundary`: 49 -> 44
- `system_interaction`: 3 -> 3
- `system_boundary_interaction`: 8 -> 3
- `system_interaction_execution_context`: 0 -> 8
- `system_interaction_match_diagnostic`: 22 -> 17
- `system_interaction_field_contract`: 231 -> 46

Per accepted interaction:
- userinfo: 1 boundary, 2 execution contexts;
- update phone flags: 1 boundary, 1 execution context;
- update/create profile: 1 boundary, 5 execution contexts.

The missing sixth update/create context is `get-or-create-profile-by-partner`. The typed boundary evidence contains the service-side path to the shared sender but not the final controller->service call edge for that observation. This remains an explicit evidence gap; KLC does not guess the missing edge.

Confidence remains `probable` for all three interactions in this checkpoint. Path case-normalization/confidence policy was deliberately not changed in the same iteration.
