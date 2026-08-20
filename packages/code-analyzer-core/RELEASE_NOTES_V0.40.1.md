# code-analyzer-core 0.40.1

## Iteration 25.1

- defers heavy Java, Python, SQL, specification and git-change analyzer imports until the corresponding CLI command executes;
- keeps `version` available without importing native analysis dependencies;
- keeps `doctor` operational when Tree-sitter wheels are missing and reports the missing provider instead of failing during CLI import;
- preserves all analysis command contracts and runtime behavior.
