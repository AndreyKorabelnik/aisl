# knowledge-layer-core 0.59.12 — end-to-end data-model lineage

Composes existing logical/storage, SQL projection/relation, structured script-call, workflow binding and PDM evidence into strict end-to-end logical-field → physical-column lineage.

New knowledge includes script materialization edges and `cross_artifact_logical_field_physical_lineage`. Traversal uses observed SQL graph and workflow-scoped materialization edges; no fuzzy field matching or UCP/datamart-specific names are used.

Fresh real validation produces 235 script-materialization rows and 334 evidence paths (212 unique logical-field→target-column correspondences). The representative `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number` path is reproduced through both current and history branches.
