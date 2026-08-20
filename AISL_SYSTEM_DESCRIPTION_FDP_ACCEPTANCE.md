# AISL System Description + Foreign Data Persistence acceptance

Date: 2026-08-15  
Status: **SYSTEM_DESCRIPTION_AND_FDP_AISL_BLOCK_COMPLETE**

## 1. Acceptance principle

This block validates two existing knowledge domains on the current canonical framework. Manual Gold is used only as an acceptance/reference source. No Gold data is used at runtime and no application-specific rules are introduced.

Evidence strength is preserved. Observed facts, supported inference, ambiguity and unresolved gaps remain distinct. The new Knowledge API projections perform no semantic derivation.

## 2. System Description — real AT900 acceptance

Target repository: AT900 `client-profile`.

Current producer path:

```text
Core system-description evidence
→ Runner
→ KLC system-description
→ knowledge_execution_result/v2
→ official Knowledge API publication
→ one pinned AISL revision
→ compact consumer read
```

Current-canonical structural result reproduces the Manual Gold dimensions:

- modules: **3**;
- inbound boundaries: **35 REST + 24 Kafka = 59**;
- outbound integrations: **13**;
- event boundaries: **34**;
- observed storage targets: **127**;
- scenarios: **59**;
- explicit entrypoint-only gaps: **26**;
- source files: **1038**;
- payload artifacts: **7/7**, coverage complete.

Representative Gold scenarios are reachable in the current typed knowledge, including:

- `TpsController.update`;
- `TpsSwitchController.changeTPSState900`;
- `RemoveDeviceConsumer.onReceive`;
- `KafkaOperatorEnrichConsumer.onReceiveMessage`;
- `ClientProfileController.phonesByCardNumber`;
- `MbClientProfileController.mbClientProfileExtended`;
- `RegistrationHistoryController.getRegistrationHistory`;
- `RegHistoryEventConsumer.onReceiveMessage`.

Conclusion: no missing observed evidence requiring a Core change and no missing knowledge composition requiring a KLC change was demonstrated.

### Real publication

After the KCP lifecycle fix described below, a fresh producer run completed and published successfully:

- job: `job-50770118bb894834aacedcdd6da37f9b`;
- status: `succeeded`;
- revision: `rev-db657fc55d3446f57adbdadd`;
- all Runner/publication stages: succeeded.

An earlier successful revision used for consumer measurement was `rev-a7fd3eb7b48b45d7718d85cc`.

### System Description consumer guidance

Added `system-description-guidance/v1` as a thin bounded projection over existing KLC query results.

Real common-case payload measurement:

- previous multi-tool context: approximately **421.5 KB**;
- compact guidance: approximately **54.8 KB**;
- reduction: **87.0%**.

The projection preserves exact KLC-owned section totals while bounding presented items. It does **not** synthesize business purpose or functional-area labels.

## 3. KCP lifecycle / artifact-index acceptance

A controlled fresh System Description run reproduced a stall after Runner completion while KCP scanned output artifacts.

Observed cause: KCP recursively hashed producer-internal Core evidence payload shards. For this real run the deep payload tree was approximately **263 MB**. This made KCP behave like a second evidence inventory instead of an orchestration/publication layer.

Generic fix in Knowledge Control Plane `1.2.0a23`:

- index the typed Core evidence descriptor owned by the official producer;
- do not recursively index/hash deep producer-internal payload shards;
- retain materialization/execution/publication artifacts normally;
- preserve payload provenance through Core/Runner-owned descriptors.

After the fix the real fresh System Description run completed and published. The resulting job artifact index contained **25 orchestration/publication artifacts** rather than recursively indexing the producer payload tree.

This is an architectural ownership fix, not a System Description-specific shortcut.

## 4. Foreign Data Persistence — real AT900 acceptance

Target repository: the same AT900 `client-profile` source, using the existing `persistence-lineage` producer/materialization.

No Core, Runner or KLC code was changed for FDP.

### Authoritative publication

The first force-run was interrupted by the external execution wrapper after Core had completed and while KLC materialization was running. It is **not** counted as PASS.

The completed Core artifact was then reused through the official content-addressed producer reuse path in a fresh output directory. No manual evidence copying or fallback was used.

Authoritative result:

- job: `job-97d120611929400bb18898da4da79537`;
- status: `succeeded`;
- revision: `rev-f165cea38d8b1456ad51c978`;
- Core producer: reused by official content identity;
- KLC `persistence-lineage`: built;
- official Knowledge API publication: succeeded;
- published capabilities: `workspace.fdp-paths`, `workspace.persistence-lineage`.

### Current canonical FDP structural result

- canonical paths: **781**;
  - source → storage: **529**;
  - storage → access: **252**;
- path maturity:
  - confirmed: **72**;
  - unresolved: **709**;
- mechanical cases: **969**;
- cases with both source and access sides: **163**;
- confirmed exact same-data cases: **8**;
- storage summaries: **88**;
- `business_fdp_decision_assigned = false`;
- `mechanical_bridge_only = true`.

These are the current canonical post-cleanup dimensions already documented by the active KLC lineage path. Older aggregate counts from earlier historical implementations are not treated as current runtime Gold.

### Representative semantic acceptance — DEVICE_LINK

For `DEVICE_LINK` the current AISL shows:

- source paths: **32**;
- access paths: **1**;
- source fields: **8**;
- access fields: **3**;
- exact overlapping storage fields:
  - `CLIENT_ID`;
  - `DEVICE_ID`;
  - `UCP_ID`;
- confirmed exact same-data cases: **3**.

Representative source:
`SyncPushDeviceConsumer.onReceive` / `SyncPushDeviceRequest`.

Representative access:
`ServerController.findDevicesByPhones`.

The technical ingress can be confirmed while `source_system` remains unresolved/null. No upstream application is guessed.

### Representative semantic acceptance — MNP / OPERATORID

Observed ingress:

`KafkaMNPConsumer.onReceiveMessage` / `PhoneMNPEvent` → `PHONE.OPERATORID`.

Exact storage-field access candidates include unresolved siblings and one confirmed end-to-end case:

`MbClientProfileController.mbClientProfileExtended`.

The framework preserves this difference instead of promoting all same-name/storage candidates to confirmed.

## 5. FDP consumer guidance

The previous common `get_fdp_landscape` read was too large for external-agent use:

- unfiltered landscape: approximately **5.33 MB**;
- `DEVICE_LINK`: approximately **1.19 MB**;
- `OPERATORID`: approximately **550 KB**.

Added `foreign-data-persistence-guidance/v1`, a thin bounded projection over existing KLC paths/cases/storage summaries.

Real measurements on `rev-f165cea38d8b1456ad51c978`:

- `DEVICE_LINK`: **1.19 MB → 69.5 KB (-94.2%)**;
- `OPERATORID`: **550 KB → 68.9 KB (-87.5%)**;
- unfiltered: **5.33 MB → 71.7 KB (-98.7%)**.

Exact summaries remain visible:

- 781 paths;
- 969 cases;
- 8 confirmed exact same-data cases;
- 88 storage summaries.

The bounded case projection prioritizes already-published confirmed same-data cases for actionability. It does not create or upgrade lineage.

## 6. Semantic boundary — important

`same_data_end_to_end_status = confirmed` means that the existing static evidence supports the technical same-data bridge required by the KLC contract. It does **not** mean that the data is legally or semantically “foreign”.

The compact read explicitly does not assign:

- upstream/source system when not observed;
- business ownership;
- legal FDP classification;
- risk verdict;
- business FDP decision.

`business_fdp_decision` remains `not_assigned` unless separately supported by an owning knowledge mechanism.

## 7. Acceptance conclusion

System Description and Foreign Data Persistence both work through the same AISL architecture without new domain-specific producers.

The proven changes in this block are consumer/read ergonomics plus one generic KCP artifact-ownership/lifecycle correction. No evidence was found that justifies modifying Core, Runner or KLC for these two domains.
