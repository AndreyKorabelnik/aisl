# AISL incremental revision snapshot + multi-case attribute-extension acceptance

Date: 2026-08-15
Status: **INCREMENTAL_REVISION_SNAPSHOT_AND_MULTICASE_ATTRIBUTE_EXTENSION_BLOCK_COMPLETE**

## Architectural acceptance

Incremental production now publishes one self-contained immutable AISL snapshot instead of a delta-only consumer revision.

```text
exact base KnowledgeRevision
+ newly produced/replaced KnowledgeProducts
→ validation + copy-on-write publication
→ one new pinned KnowledgeRevision
```

Rules proven by executable contract and Knowledge API:

- `base_revision_id` is explicit; active/latest is never guessed.
- Same-system `external_knowledge_artifacts[]` require the exact base revision.
- Unchanged base products are retained by exact published artifact identity; their bytes/digests are revalidated, not rebuilt or copied.
- Newly produced products replace the base product slot owned by the same `source_materialization_id`.
- Capabilities are derived from the final composed snapshot.
- Cross-system dependencies remain provenance only and are not silently imported into the target snapshot.
- Consumers still use exactly one pinned revision. No multi-revision read adapter was introduced.

## Real composed revision acceptance

System: `aisl-attribute-extension-final`

- base revision: `rev-1ef19edb4b8f99f927b30e38`
- composed revision: `rev-1fed54320afb0632c144e098`
- products: **8**
- capabilities: **44**
- integration profile: `attribute-addition-plan/v1`, profile version **12**
- exposed tools: **17**
- profile scope: composed revision, `revision_binding=pinned`

The base full 8-product execution and the incremental `data-model-attribute-extension-context` execution were published through the official Knowledge API. The composed revision retained the seven unchanged product slots and replaced only the derived context slot.

## Multi-case usefulness acceptance

All reads below were performed through the composed revision HTTP surface.

| Case | Observed relationship confidence | Consumer usefulness | Result |
|---|---|---|---|
| `PartyToPartyGroup.partyGroup → PartyGroup` | confirmed | confirmed / existing SQL JOIN | reuse observed JOIN |
| `PhoneNumber.mobileOperator → UcpMobileOperator` | strongly_supported | probable / proposed SQL JOIN | target SQL representation still required |
| `Address.flags → ContactFlag` | confirmed, many | strongly_supported / collection navigation | preserve/reduce multiplicity explicitly |
| `Individual.partyToPartyGroups → AbstractPartyToPartyGroup` | confirmed, many, polymorphic | ambiguity | 11 concrete targets; subtype/representation must be selected |
| `UserInfo.bankInfo → BankInfo` | confirmed | probable / direct reference | physical SQL representation must be confirmed |
| `ApprovalInfo.approver → UserInfo` | unresolved | unresolved | inspect missing storage/SQL evidence |

Scalar control: `BirthPlace.value` produces no false relationship context. SQL target resolution still selects `epk_client`; insertion selects `stg_epk_client_birthplace_snp.sql` with `propagation=resolved`.

Additional SQL insertion observations preserve useful uncertainty:

- birthplace/region: target `epk_client`, score 144; insertion score 167, propagation resolved; `regioncode` is not claimed as an already observed source column.
- party-group: target score 159; insertion score 190, propagation resolved.
- phone/mobile operator: insertion points to the phone-number staging scope, propagation partial, with explicit missing exact end-to-end dependency diagnostic.
- address/flags: insertion points to the address staging scope, propagation partial, with the same explicit dependency limitation.

## Conclusion

The attribute-extension scenario is now self-contained behind one AISL revision and produces materially different, evidence-calibrated guidance rather than flattening all relations into confirmed JOINs. No Core, Runner, KLC, Prepared Runtime or Knowledge Integration implementation change was required in this block.
