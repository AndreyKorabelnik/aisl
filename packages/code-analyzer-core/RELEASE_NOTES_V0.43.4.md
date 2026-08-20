# code-analyzer-core 0.43.4

Version 0.43.4 propagates complete intermediate output contracts through qualified wildcards and single-source unqualified wildcards.

## Supported wildcard provenance

A wildcard projection can expand a contract only when its source relation is uniquely identified and already has a complete SQL-derived output contract:

- `alias.*` resolves through one exact same-scope intermediate alias;
- `*` resolves only when one non-generated relation is present in the scope;
- multi-level CTE/derived wildcard chains are expanded to a fixed point.

Each expanded scope and relation records bounded wildcard provenance with the source relation and resolution basis.

## Safety boundary

The implementation does not expand:

- wildcard projections from physical or physical-template relations without an external schema;
- unqualified `*` over multiple relations;
- wildcard contracts that introduce duplicate output names;
- recursive wildcard cycles without a complete seed;
- set-operation contracts, which remain deferred.

An explicit CTE/derived column list no longer makes `SELECT *` over an unknown physical schema complete merely because the AST contains one wildcard expression.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 236 CTE/derived relations gained complete wildcard-propagated contracts;
- 14 additional column usages were resolved;
- `ambiguous_unqualified` decreased from 263 to 249;
- resolved source-field usages increased from 10,796 to 10,810;
- source-field resolution increased from 97.6042% to 97.7308%;
- seven projections changed from partial to resolved.

The unchanged 30-file SQL Source Inventory quality fixture remains fully green.
