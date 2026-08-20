# Canonical relationship storage model v2

`knowledge-layer-core 0.28.0` exposes one nested, facts-only relationship contract:

- `source`: source object/field/cardinality;
- `target.logical_identity`: observed identity, version and collocation roles;
- `target.storage_key`: observed physical storage-record key fields, expressions and provenance;
- `target.aliases`: observed target aliases;
- `reference.encoding_inputs`: type component from target alias and key component from target storage key;
- `reference.physical_encoding.status`: whether physical formatting is observed or requires downstream interpretation;
- `join`: structured join status and endpoints.

KLC does not normalize aliases, insert separators, generate SQL or promote an interpretation to a confirmed physical join. It fails closed when storage evidence cannot be attached uniquely. The old flattened `join_guidance` and `target_key_fields` response fields are not part of this contract.
