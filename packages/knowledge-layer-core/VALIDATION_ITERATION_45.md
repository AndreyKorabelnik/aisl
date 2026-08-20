# Real-application validation — iteration 45

The frozen databases from the manual-versus-framework comparison were copied. Only
`repository_value_node` and `repository_value_flow_edge` were rematerialized using 0.48.0;
boundary matching results were not edited.

## Multi-repository result

- matched boundary interactions: 8;
- all eight remained `probable`;
- transport edges before: 0;
- candidate transport edges after: 226;
- request transport edges: 226;
- confidence promotions: 0.

## updatePhoneFlags result

- matched probable interactions: 1;
- candidate transport edges: 2;
- matched wire paths: `phone`, `sberProfileId`.

The evidence packet records exact method/path/property matching, the unique indexed target,
loopback authority as non-binding, payload type inequality and partial request-contract
coverage. No conflicting real authority was observed.

Nested fields under `phone.flags[]` remain outside the source wire contract and are the next
coverage gap.
