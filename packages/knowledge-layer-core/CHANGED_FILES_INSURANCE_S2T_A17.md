# Insurance S2T generic support — 0.61.0a17

- preserve Jinja root placeholders during workflow file normalization so repository-local literal suffix matching works;
- compose exact sibling workflow parameters (`name` + `prior_value/value`) for existing producer observations;
- allow explicit observed `s2tTableList` output to anchor existing workflow target lineage;
- preserve useful complete direct-producer contracts when sibling branches are incomplete, with explicit gap;
- do not classify unresolved source-relation placeholders as resolved physical identities.

No app/table-specific names or Gold data are used by runtime logic.
- 0.61.0a18: publish visible build diagnostics for observed-materialization / zero-mapping outcomes and propagate manifest diagnostics through the generic materialization runtime.
