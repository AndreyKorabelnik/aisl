# code-analyzer-core 0.40.6

Iteration 28.2E resolves constructor provenance that is deterministically observable from Java lexical scope and exact API semantics, while leaving unknown helper/DAO return contracts unresolved.

## Changes

- preserves Tree-sitter local declarations without initializers, allowing branch-assigned local values to remain distinguishable from class fields;
- resolves constructor arguments passed through method-local values without inventing the origin of helper return values;
- resolves lambda parameters only inside the exact containing lambda byte span;
- resolves jOOQ `Record.getValue(Field)` from the observed `Field` declaration and literal `field("name", Type.class)` initializer;
- recognizes only import-proven JDK `Collections.emptyMap/emptyList/emptySet` calls as observed empty defaults;
- derives same-class copy-constructor expressions from explicit enclosing class fields;
- resolves `Optional.orElse/orElseGet/orElseThrow` as an observed optional-value unwrap when the receiver has an `Optional<T>` declaration;
- preserves source-kind and resolution provenance on emitted mapping/derivation facts;
- keeps direct DAO/helper calls unresolved when no return contract is observed.

The implementation is repository-neutral and relies on AST spans, lexical declarations, imports, declared Java types and exact API forms. It contains no AT900/UCP, package, class or field-name conditions.
