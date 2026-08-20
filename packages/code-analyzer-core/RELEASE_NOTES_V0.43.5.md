# code-analyzer-core 0.43.5

Version 0.43.5 adds branch-aware output contracts for SQL set operations.

## Set-operation contract

For `UNION`, `UNION ALL`, `INTERSECT` and `EXCEPT`:

- every output branch is preserved with its scope, ordinal, names and status;
- external output names come from the first branch, following SQL semantics;
- source lineage continues to preserve every branch by output ordinal;
- a relation becomes complete only when all branches are complete and have equal cardinality;
- explicit CTE/derived column lists may rename a complete set contract when their count matches.

## Diagnostics

Partial contracts carry local diagnostics instead of failing analysis:

- `set_operation_branch_incomplete`;
- `set_operation_cardinality_mismatch`;
- `explicit_output_column_count_mismatch`.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 72 relations gained complete set-operation contracts;
- one relation remained partial because one branch was incomplete;
- six additional column usages were resolved;
- `ambiguous_unqualified` decreased from 249 to 243;
- resolved source-field usages increased from 10,810 to 10,816;
- source-field resolution increased from 97.7308% to 97.7850%;
- four projections changed from partial to resolved.

The unchanged 30-file SQL Source Inventory quality fixture remains fully green.
