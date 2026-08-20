# code-analyzer-core 0.43.18

## Custom factory method-reference provenance

- Factory setter mappings now resolve nested getter paths back to the factory method parameter.
- Local aliases such as `Card card = request.getData()` preserve the complete source path.
- Getter evidence nested in wrappers such as `Optional.ofNullable(...).map(...).orElse(...)` is retained.
- `Collectors.toMap(..., this::factoryMethod, ...)` value projections can now use source-declared factory field mappings for a requested target field.
- Factory lookup is constrained by exact method name, requested target field, and caller class/qualifier.
- No persistence or business conclusion is created by the factory mapping alone; it remains technical propagation evidence until connected to a physical write.
