# Test results — code-analyzer-core 0.44.0

- Focused final evidence/runtime suite: 18 passed.
- Earlier broader storage/SQL evidence suite in the same working tree: 23 passed.
- Cross-module Core/Runner/KLC execution smoke: passed.
- `compileall`: passed.
- Offline dependencies only; no network installation.
- Full Core regression was not run because Java and SQL parser algorithms were reused; changes are limited to generic analyzer registration, envelopes, contract catalog, and removal of the public legacy SQL command.
