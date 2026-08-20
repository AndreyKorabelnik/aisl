# Test results — static-analysis-runner 0.9.52

- Focused final planning/execution/CLI suite: 39 passed.
- Earlier broader targeted Runner suite in the same working tree: 67 passed.
- Real generic `knowledge-execute`: 2 Core analyzers, 2 KLC materializations, 2 knowledge artifacts, 13 capabilities — passed.
- `compileall`: passed.
- Full Runner regression was not required because the common executor was not redesigned; the removed SQL-specific route and source-language compatibility were covered directly.
