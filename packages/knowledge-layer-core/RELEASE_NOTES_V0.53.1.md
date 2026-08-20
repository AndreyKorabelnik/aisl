# knowledge-layer-core 0.53.1

Adds a deterministic read-only query surface over the typed `physical-model/v1` materialization introduced in 0.53.0.

Available queries cover:

- physical-model summary and coverage counts;
- table search by physical/logical name, code and observed column name/code;
- table details with columns, keys and inbound/outbound relationships;
- paged column, key, relationship and gap inventories;
- deterministic continuation tokens bound to filters.

The query layer does not infer source/target roles from PDM. SQL-observed `read` and `write` usage remains authoritative.
