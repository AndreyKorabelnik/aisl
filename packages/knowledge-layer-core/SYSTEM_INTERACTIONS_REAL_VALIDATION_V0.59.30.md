# Real validation — system interactions — KLC 0.59.30

Workspace:
- `sbpr-ucp-intergation`
- `gateway-sberid-userinfo-by-ucpid`
- `gw-sberid-update-phone-flags`
- `gw-sberprofile-create-update-extprofile`

Baseline Core evidence: 0.44.16, reused unchanged.
Manual Gold: `system-interactions-manual-gold-1.0.0-2026-08-08.zip`, SHA-256 `c0e30808f0cc8ebcde87b60f70f4b98d8f20ce32e3f97b046cf0b8cd2ae37786`.

## Real result

- `repository_interaction_boundary`: 44
- `system_interaction`: 3
- `system_boundary_interaction`: 3
- `system_interaction_execution_context`: 8
- `system_interaction_match_diagnostic`: 17

Accepted technical matches:
1. userinfo: `/sberProfileId/search` -> `/sberProfileId/search`, `path_basis=exact_path`, confidence `probable`, address basis absent;
2. update phone flags: `/updatePhoneFlags` -> `/updatePhoneFlags`, `path_basis=exact_path`, confidence `probable`, address basis absent;
3. update/create: `/ucp/updateOrCreate` -> `/updateOrCreate`, `path_basis=normalized_path`, confidence `probable`, address basis absent.

The shared update/create source boundary still preserves both observed source path variants:
- `/UpdateOrCreate`
- `/ucp/updateOrCreate`

The case-only `/UpdateOrCreate` variant is no longer treated as an exact match to target `/updateOrCreate`.

Confidence policy is intentionally unchanged in this checkpoint. The lack of target-side addressing identity remains visible as `probable` instead of being promoted by path similarity alone.
