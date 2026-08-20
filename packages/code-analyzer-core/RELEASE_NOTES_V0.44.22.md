# code-analyzer-core 0.44.22

Architecture-boundary audit cleanup.

- Reference-data typed evidence now owns the explicit internal pipeline identity `internal-reference-data-evidence-v1`; the stale `internal-subject-knowledge-evidence-v1` identity and `subject-knowledge-payload` naming are removed.
- The broad reference-data pipeline is intentionally retained because the artifact uses observed declared values, storage operations, joins, source-to-storage lineage, ingress/jobs, external dependencies and unresolved gaps. No evidence semantics or record filtering were reduced.
- Core target-contract assessment now classifies stage dependencies and analyzer-owned pipeline state as internal implementation diagnostics rather than dependencies between public evidence analyzers.
- Public evidence-analyzer compliance remains about typed artifact boundaries and the absence of Knowledge materialization inside Core.
- No compatibility alias or dual path was added.
