# Real validation — system interactions value flow — KLC 0.59.31

Workspace:
- `sbpr-ucp-intergation`
- `gateway-sberid-userinfo-by-ucpid`
- `gw-sberid-update-phone-flags`
- `gw-sberprofile-create-update-extprofile`

Inputs reused without changing Core:
- Core 0.44.16 evidence;
- KLC 0.59.30 system-interactions result;
- KLC 0.59.30 interaction-field-contracts result;
- repository-value-flow/v6 baseline.

Result after rematerializing `cross-repository-value-flow` with KLC 0.59.31:
- repository value nodes: 25,037;
- repository value-flow edges: 20,155;
- cross-repository transport edges: 46.

By accepted boundary:
- userinfo: 2 transport edges;
- update phone flags: 7 transport edges;
- update/create profile: 37 transport edges.

The prior 37-contract/0-transport update/create gap is therefore closed.

Root cause confirmed:
`system-interactions` correctly created a KLC-owned `composed_http_outbound_boundary_*` identity, while value-flow previously created wire nodes only for raw Core `interface_*` identities. Downstream lookup by the composed ID therefore had no source wire node. The fix materializes wire nodes for the composed identity itself.

Separate unresolved observation:
`name.surname` has the correct cross-boundary transport edge but no observed source-local incoming value-flow edge into the composed source wire node. This checkpoint does not infer or fabricate that local segment.
