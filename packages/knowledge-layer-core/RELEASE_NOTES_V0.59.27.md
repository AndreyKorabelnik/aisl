# knowledge-layer-core 0.59.27

FDP read-side enrichment only; persistence materialization semantics are unchanged.

`ForeignDataPersistenceQueryService` no longer drops technical source-kind knowledge already present in typed evidence. Confirmed Kafka/REST/external-service source→storage paths are surfaced as `confirmed_external_ingress`; unresolved external boundaries remain candidates; method inputs remain runtime-input candidates; local/generated origins remain separate.

This is **not** a business ownership or FDP-risk verdict. The exact upstream system may remain unknown and is explicitly treated as a governance question rather than a technical blocker.

Real AT900 reporting dataset: 53/120 selected paths now carry source interpretation instead of 0/120; representative Kafka FDP paths are classified as confirmed technical ingress.
