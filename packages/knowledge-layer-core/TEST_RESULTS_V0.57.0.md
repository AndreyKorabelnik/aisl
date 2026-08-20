# Test results — knowledge-layer-core 0.57.0

- Focused final materialization/runtime suite: 31 passed.
- Earlier broader storage/SQL materialization suite in the same working tree: 44 passed.
- Real generic Core → Runner → KLC execution: passed.
- `compileall`: passed.
- Offline DuckDB and SQLGlot wheels only.
- Full KLC regression was not run because the common runtime mechanism was unchanged; the two new handlers and SQL capability publication were tested directly.
