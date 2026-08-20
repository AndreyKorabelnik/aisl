# code-analyzer-core 0.44.13

## System Description scenario composition

System Description now composes inbound REST/Kafka scenarios with existing source-declared call observations and reachable storage/outbound boundaries.

Key points:
- streams only the required call-graph observation sections from the existing uncapped source observation fact store;
- does not raise navigation preview limits or rehydrate the complete observation store;
- exact cross-module, same-owner and exact field-type call resolution only;
- only a unique non-test declared implementation is traversed; ambiguous implementation sets remain unresolved;
- compact system scenarios now retain bounded call-chain/provenance fields.

The `system-description-evidence/v1` contract is unchanged. No business-process inference is introduced.
