# code-analyzer-core 0.44.10

Golden Knowledge regression exposed a generic SQL template parsing gap: an optional SQL fragment placeholder placed on its own line after a complete FROM relation could be interpreted as an alias/token by SQLGlot, leaving only the first CTE in the scoped AST.

0.44.10 removes only that unknown fragment from the parser view while retaining the placeholder as semantic evidence. Relation placeholders, SELECT-list placeholders and other value placeholders remain explicit and are not erased.
