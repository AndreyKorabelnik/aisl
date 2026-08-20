# code-analyzer-core 0.43.6

Version 0.43.6 adds universal repository-local materialized relation contracts.

## Schema-defining evidence

A physical relation receives a complete output contract only from:

- explicit `CREATE TABLE` / `CREATE VIEW` columns;
- a complete CTAS or view source scope;
- `CREATE TABLE ... LIKE ...` when the source relation already has a complete contract.

File-local literal/template bindings may resolve target and `LIKE` source identities. Matching remains exact after resolution.

Ordinary `INSERT` statements are preserved as observed writes and never treated as proof of a complete physical schema. Conflicting DDL definitions remain partial.

## Contract propagation

Complete repository-owned physical schemas are propagated to later exact reads. Existing wildcard CTE/derived contracts can then be completed, and unqualified fields are resolved only when every relation in the scope has a complete contract and exactly one relation owns the field.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 11 logical physical relations received complete repository-local schemas;
- 18 wildcard CTE/derived occurrences became complete;
- 38 additional column usages were resolved;
- `ambiguous_unqualified` decreased from 243 to 205;
- resolved source-field usages increased from 10,816 to 10,854;
- source-field resolution increased from 97.7850% to 98.1286%;
- partial recursive lineage paths decreased from 140 to 29;
- scoped/recursive gaps decreased from 183 to 72.

The unchanged 30-file SQL Source Inventory quality fixture remains fully green.
