# code-analyzer-core 0.44.23a7

Corrects the Core-owned preflight applicability declaration for `data-model-candidate-evidence`.

The candidate scanner is not Java-only: it also observes declarative schema files, SQL DDL/migration files, and model-oriented repository paths. Therefore a Java-only predicate could incorrectly authorize a hard skip and discard observed candidate evidence. The contract now keeps applicability explicitly `not_formalized` until a safe source-landscape predicate can represent the scanner's full input domain.

No candidate scanner semantics changed. Missing applicability remains visible and Runner must preserve execution rather than hard-skip.
