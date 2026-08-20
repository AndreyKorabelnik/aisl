# code-analyzer-core 0.40.5

Iteration 28.2D resolves constructor argument provenance that was already observable in the same Java method.

## Changes

- recursively follows local variable declarations used as constructor arguments;
- records direct method-parameter and implicit class-field pass-through;
- represents literal/default and conventional named-constant assignments as observed derivations rather than missing mappings;
- represents explicit nested object creation as an observed constructor origin and records its parameter inputs;
- preserves the raw constructor argument, resolved source expression and resolution kind in remaining gaps;
- keeps no-source observed origins from test/generated code out of the production evidence stream;
- adds `class_field_types` to the internal Tree-sitter method index so local variables and implicit fields are not conflated.

The implementation is repository-neutral and uses AST, lexical declarations and Java source context only. It contains no AT900/UCP, package, class or field-name conditions.
