# Test status — knowledge-layer-core 0.59.41

- KLC targeted typed/materialization suite: **35 passed**.
- Affected Runner execution/materialization suite against KLC 0.59.41: **27 passed**.
- Negative compatibility tests: generic-only `analysis_record` rejected by repository value-flow, system interactions, and interaction field contracts.
- Compileall: passed.
- Import/materialization registry smoke: passed; 19 materializations registered.
- Active-source audit: zero `analysis_record` occurrences across current module source trees.
- Full multi-module regression intentionally not run for this focused KLC contract cut.
