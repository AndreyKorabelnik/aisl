# code-analyzer-core 0.43.3

Version 0.43.3 introduces explicit output contracts for SQL intermediate relations and uses them to resolve unqualified columns only when ownership is fully proven inside SQL.

## Output contracts

Every SELECT scope now publishes its observed output columns and contract status. CTE and derived relations inherit a complete contract only when:

- every projection has a deterministic output name;
- no wildcard projection is present;
- no duplicate output name is present;
- the relation has one definition scope in this iteration;
- an explicit CTE/derived column list, when present, is unique and matches the projection count.

Set-operation contracts remain partial and are deferred to the dedicated UNION iteration.

## Resolution rule

An otherwise `ambiguous_unqualified` usage is bound to an intermediate relation only when:

1. every non-generated relation visible in the current SELECT is a CTE or derived relation;
2. every visible relation has a complete SQL-derived output contract;
3. exactly one contract contains the referenced field.

Physical tables, templates, wildcard contracts, duplicate output names and incomplete definitions prevent resolution. No table schema is inferred from absence of a field.

Resolved usages record:

- `resolution_basis = unique_complete_intermediate_output_contract`;
- `resolution_contract_status = complete`;
- `resolution_contract_basis` from the defining SQL contract.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 54 usages were resolved by complete intermediate output contracts;
- `ambiguous_unqualified` decreased from 317 to 263;
- resolved source-field usages increased from 10,742 to 10,796;
- source-field resolution increased from 97.116% to 97.6042%;
- 53 projections and one JOIN gained a deterministic relation binding;
- no recursive-lineage or gap count was changed by this step.

The unchanged 30-file SQL Source Inventory quality fixture remains fully green: 30/30 cases and 100% relation, classification, field and role quality gates.
