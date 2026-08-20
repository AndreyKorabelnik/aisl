# knowledge-layer-core 0.59.13 — workflow dependency lineage

Adds evidence-backed workflow-to-workflow composition on top of existing SQL/script materialization knowledge. No Core workflow analyzer changes were required: KLC composes already observed workflow bindings.

Real Gold anchor now closes:
`BirthPlace.value → epk_client.birth_place` with two observed current/history paths.

Existing `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number` remains two paths.
