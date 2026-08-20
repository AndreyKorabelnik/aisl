# code-analyzer-core 0.44.23a2

S2T observed-call completeness increment on top of 0.44.23a1.

## Change
- A leading SQL-style comment no longer prevents an otherwise observed top-level DSL invocation from being classified and published as `sql_script_call`.
- The call symbol and arguments remain syntax evidence only; Core assigns no transform/business semantics.

## Genericity
No application names, table names, Gold rows, aliases, or call-specific business semantics are introduced.
