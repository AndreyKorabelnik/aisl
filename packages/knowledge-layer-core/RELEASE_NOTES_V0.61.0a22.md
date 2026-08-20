# Knowledge Layer Core 0.61.0a22

Branch-aware S2T and scoped placeholder resolution.

- Preserves distinct observed SQL UNION/query branch identity through producer traversal and target lineage.
- Extends `sql-target-source-mapping/v2` with branch relation, branch scope/ordinal, branch-local terminal driver relation, driver status/basis/candidates, and source relation role/basis.
- Derives a driver only when one unique terminal source relation is observed on a driver path inside the branch. Multiple candidates remain ambiguity; zero candidates remain unresolved.
- Classifies terminal source relations as `driver_path`, `enrichment`, `driver_candidate`, or `unknown` from observed FROM/JOIN path structure. These roles are derived knowledge, not Core observed facts.
- Resolves `${$...}` source relation placeholders recursively from exact scoped workflow parameter environments and exact config-to-SQL references. Environment-dependent placeholders such as `{{src_sbs_schema_name}}` remain visible when no stand is selected.
- Keeps branch identity during terminal aggregation and preserves distinct effective transformations.
- No Core analyzer/schema change and no new producer/materializer/resolver path.

Real `custom_b2c_insurance` acceptance: 6,987 raw mappings, 1,905 value mappings, 4,052 explicit gaps. Branch-aware export: 3,330 rows / 24 target tables / 652 target fields. Remaining `${$app...}` in exported `source_relation`: 0.

Examples: SBS `t_dim_accrual.accrual_dt` -> `{{src_sbs_schema_name}}.policyaccruals.data`, branch driver `{{src_sbs_schema_name}}.policyaccruals` (partial only because environment schema is unresolved). `policyaccrualdetails` fields are enrichment in that SBS branch. SBSZH driver is `{{src_sbszh_schema_name}}.pay`. ASBS remains unresolved where current evidence does not identify one unique terminal driver.

Affected regression: 64/64 PASS. Full KLC suite not completed in this block and is not reported as PASS.
