# Canonical relationship storage model v1

`knowledge-layer-core 0.26.0` keeps logical model identity and physical storage references as separate evidence surfaces.

## Logical identity

Logical identity is sourced from observed model-key roles. A member whose observed role contains `version` is classified as a version member; a role containing `collocation` is classified separately; remaining observed key roles are identity members. Classification uses annotation/key roles, never field-name heuristics.

Query surface:

- `v_model_relationship_logical_identity_members`
- `WorkspaceKnowledgeQuery.model_relationship_logical_identity_members(...)`
- `target_logical_identity` in raw `WorkspaceKnowledgeQuery.model_relationships(...)`

## Physical storage reference

A physical storage reference preserves:

- source object and source field;
- target alias;
- physical storage-key field and expression;
- storage-record occurrence when uniquely resolvable;
- reference value expression and scope-aware binding resolution;
- target converter operation;
- return/reference value origin;
- type/key sources;
- parameter binding path;
- exact source provenance;
- downstream physical-encoding requirement.

Query surface:

- `model_relationship_storage_reference`
- `v_model_relationship_storage_references`
- `WorkspaceKnowledgeQuery.model_relationship_storage_references(...)`
- `storage_references` in raw `WorkspaceKnowledgeQuery.model_relationships(...)`

## Attachment rule

A storage-reference observation is attached only when `(source object FQCN, source field, observed target alias)` identifies exactly one canonical relationship. Polymorphic concrete targets participate in the same exact matching. Zero or multiple matches produce no materialized attachment.

## Deliberate boundary

KLC does not:

- normalize aliases;
- insert type-prefix separators;
- infer `type_prefixed_key`;
- generate SQL or `CONCAT`;
- claim a physical join is confirmed.

The raw facts state `physical_encoding=downstream_interpretation_required`. A downstream LLM or another consumer may interpret the physical format using a separate domain prompt while retaining KLC provenance.
