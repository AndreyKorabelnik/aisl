# S2T useful-surface checkpoint — KLC 0.61.0a8

Generic changes accumulated after 0.61.0a7:
- preserve exact file-reference candidate sets for embedded placeholders without guessing placeholder values;
- guard against overly broad whole-directory wildcard expansion and Cartesian ambiguity multiplication;
- reuse existing observed producer traversal for cross-SQL-unit target lineage;
- allow a complete observed target contract to be exposed as partial/probable at the final target anchor when sibling observed branches are incomplete, preserving diagnostics;
- observe exact script-loop query/output pairs when they are correlated by a literal list and loop index;
- seed the existing sql-target-source-mapping from exact observed query -> output materializations in addition to workflow targets;
- resolve a concrete terminal table component from observed local/workflow bindings while leaving unresolved schema placeholders unresolved.

No Gold/table/application-specific rules were added. No new analyzer, materializer, API, or parallel lineage runtime was introduced.
