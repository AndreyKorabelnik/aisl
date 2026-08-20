# knowledge-layer-core 0.38.0

## Repository interaction islands

- Added strict weakly connected components from confirmed repository interaction edges.
- Added extended components from confirmed plus probable edges.
- Added one-node components for isolated repositories.
- Added deterministic island and member identities.
- Added directed inbound, outbound and total degree statistics per member.
- Added coverage status, protocol summaries and confirmed/probable edge counts.
- Added paginated query and evidence-tool surfaces for islands and members.
- Added a synthetic regression fixture covering `A → B ← C`, probable `D → E`, and isolated `F`.
