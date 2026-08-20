# Analysis UI 2.0.0a36

Iteration 111 final synchronization with Knowledge Assistant 0.14.3 and attribute-addition profile content version 2.

- Standard prepared-context chat keeps loading the complete public profile on every exchange.
- The dependency floor is raised to `knowledge-assistant>=0.14.3,<0.15.0`.
- Diagnostics expose profile version `2` and the new SHA-256 fingerprint.
- Five real-evidence answer classes are stored as validation artifacts: existing JOIN, one new JOIN, two new JOINs, collection cardinality and multiple target candidates.
- No frontend source or repository-editing capability was added.
