# code-analyzer-core 0.43.2

Version 0.43.2 resolves later unqualified references to direct projection aliases without using external schemas or name guessing.

## Canonical rule

An unqualified column usage may inherit a relation binding only when all of the following are true:

1. the current usage is otherwise `ambiguous_unqualified`;
2. an earlier projection in the same SELECT scope publishes the same output name;
3. that earlier projection is a direct passthrough of one qualified column, for example `dd.active_flag AS active_flag`;
4. the qualified source resolves by an exact same-scope alias;
5. exactly one prior direct projection alias matches.

Computed aliases, later aliases, outer-scope aliases and multiple candidates remain unresolved.

Each inferred usage records:

- `resolution_basis = prior_direct_projection_alias`;
- `resolution_source_projection_id`;
- `resolution_source_column_usage_id`.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 48 usages were resolved by the new rule;
- `ambiguous_unqualified` decreased from 365 to 317;
- resolved source-field usages increased from 10,694 to 10,742;
- source-field resolution increased from 96.682% to 97.116%;
- partial recursive lineage paths decreased from 176 to 140;
- scoped lineage gaps decreased from 219 to 183.

All four cases identified by the external GPT trial are now resolved deterministically.

The unchanged 30-file SQL Source Inventory quality fixture remains fully green: 30/30 cases and 100% relation, classification, field and role quality gates.
