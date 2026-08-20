# AISL Reference Data / NSI — real acceptance and consumer guidance

Date: 2026-08-16  
Status: **REFERENCE_DATA_AISL_BLOCK_COMPLETE**

## 1. Acceptance principle

This block validates the existing Reference Data / NSI knowledge domain on the current canonical framework. Manual Gold is used only as an acceptance/reference oracle and is not a runtime source.

The framework remains evidence-first. It publishes technical facts and context but does not silently assign enterprise/business ownership, global definition authority or an official own-NSI verdict.

## 2. Existing production path

The official route already existed and was reused unchanged:

```text
Core reference-data analyzer
→ typed reference-data-evidence/v1
→ Runner
→ KLC reference-data/v1
→ knowledge_execution_result/v2
→ official Knowledge API publication
→ one immutable pinned AISL revision
→ consumer-only Reference Data profile
```

No new producer, parser or materializer was added.

## 3. Real AT900 production acceptance

Target repository: AT900 `client-profile`.

A fresh force-run completed the Core producer and persisted the official content-addressed evidence artifact. The external execution wrapper expired before the parent one-shot completed, so that first invocation is **not counted as PASS**.

The authoritative replay used the official content-addressed reuse path. No evidence was copied manually and no fallback path was introduced.

Authoritative result:

- system: `at900-client-profile-reference-data`;
- job: `job-2d8e2dd6fada45668205498e59ac5005`;
- status: `succeeded`;
- published revision: `rev-7e8a9ec88020277028ac41cb`;
- Core exact producer artifact reused by content identity;
- Core saved time reported by KCP: **63.147 s**;
- KLC `reference-data` materialization: **65.697 s**;
- publication: **PASS**;
- capabilities:
  - `common.declared-value-sets`;
  - `common.reference-data`;
  - `common.reference-data-facts`.

KLC materialization coverage:

- schema: `reference-data/v1`;
- status: complete;
- subject knowledge records: **21,828**;
- sections: **15**;
- source files: **1,038**.

Current Core observed counts reproduce the previously accepted Reference Data run, including:

- persistence facts: **7,104**;
- persistence lineages: **529**;
- data model facts: **14,113**;
- data model attributes: **2,496**;
- data model mappings: **1,735**;
- declared value sets: **157**;
- declared value facts: **1,521**;
- normalized facts: **50,462**;
- persisted facts: **20,675**.

## 4. Frozen 22-case semantic Gold

The frozen acceptance contains:

- strong own-NSI candidates: **7/7**;
- borderline candidates: **4/4**;
- negative/external controls: **11/11**;
- total semantic cases: **22/22**.

Strong cases:

- `PRODUCT_PRICE`;
- `TERBANK`;
- `MOBILEOPERATOR`;
- `SBRF_BIN`;
- `PHONE_BLOCK_CODE`;
- `LINK_NOTIFICATION_STATE`;
- `TARIF`.

Borderline cases:

- `LINK_BLOCK_CODE`;
- `PAYMENT_BLOCK`;
- `TARIF_AMKM`;
- `CELEBRATION`.

Controls include runtime/configuration/value-set near-misses and the external MNP `operatorId` occurrence.

The current pinned revision was tested with all **25 technical token queries** underlying these 22 cases.

Current structural diff:

- semantic-definition dimensions exact: **25/25**;
- policy guards exact: **25/25**;
- candidate representation counts: preserved;
- observed definition modes: preserved;
- local-definition evidence counts: preserved;
- literal-write structure: preserved;
- coverage count changes are treated as non-semantic unless they change classification evidence.

The required policy guards are still explicit for every query:

- `reference_semantics_assigned = false`;
- `own_nsi_status_assigned = false`;
- `global_definition_authority_established = false`;
- `human_or_llm_interpretation_required = true`.

Conclusion: **no Core evidence gap and no KLC semantic-composition gap were demonstrated**.

## 5. Critical external/local boundary

The MNP `operatorId` control remains deliberately distinct from the local `MOBILEOPERATOR` dictionary evidence.

For `operatorId` the current technical context shows:

- local candidate representations: **0**;
- local definition evidence: **0**;
- observed literal writes: **2**;
- Kafka/ingress usage is visible, including `KafkaMNPConsumer.onReceiveMessage` / `PhoneMNPEvent`;
- no local definition authority is manufactured.

A separate query for `MOBILEOPERATOR` shows a local source-seed definition.

Therefore the framework does not infer that an externally arriving operator identifier and a locally defined operator dictionary have the same origin/ownership merely because their subject matter overlaps.

## 6. Consumer ergonomics gap

The semantic knowledge was correct, but the existing common consumer path was too large for an external LLM.

Measured on the real pinned revision before the change:

- unfiltered `get_reference_data_landscape`: **2,749,405 B**;
- `PRODUCT_PRICE` landscape/context: approximately **284,803 B**;
- `operatorId` landscape: **978,976 B**.

The Reference Data profile also instructed the agent to start with the broad landscape read.

This is a consumer/read problem, not a producer gap.

## 7. Compact Reference Data guidance

Added `reference-data-guidance/v1`, a thin bounded projection over already published KLC facts.

Common tool:

`get_reference_data_context`

Modes:

- no token → compact discovery catalog;
- token supplied → exact technical context with KLC-owned totals and bounded representative evidence.

The projection retains:

- representation identity and kinds;
- definition modes;
- local-definition evidence;
- literal writes;
- usage-kind summary;
- bounded representative usage observations;
- bounded gaps;
- evidence/provenance identifiers;
- interpretation policy.

It explicitly reports:

`projection.semantic_derivation = none`.

It does **not** derive:

- official reference semantics;
- enterprise/global definition authority;
- own-NSI status;
- source-of-truth ownership.

Detailed existing Reference Data tools remain available for drill-down.

## 8. Real compactness acceptance

On `rev-7e8a9ec88020277028ac41cb`:

- global discovery: **2,749,405 B → 91,236 B (-96.7%)**;
- `PRODUCT_PRICE`: **~284,803 B → 33,291 B (-88.3%)**;
- `operatorId`: **~978,976 B → 34,300 B (-96.5%)**.

The `operatorId` compact view still exposes external ingress evidence while retaining zero local-definition evidence. The compactness improvement therefore does not erase the key semantic boundary.

Live Integration Profile acceptance:

- profile: `reference-data/v1`;
- profile version: **2**;
- tool catalog version: **8**;
- tools: **10**;
- all tools pinned to the same revision;
- default common path starts with `get_reference_data_context`;
- raw/detailed reads are drill-down, not the default first step.

## 9. Limitations / explicit non-claims

- AISL does not declare a candidate to be official enterprise NSI solely from local technical definition evidence.
- Absence of an upstream/global definition in the inspected repository is not proof that none exists.
- `candidate`, `probable`, local seed, enum, literal table or dictionary-like naming must not be silently promoted to official ownership.
- Coverage counts may expand when a broader exact technical query is used; this is not itself a semantic classification change.
- No real external-LLM behavioral trace was run after this compact-read change. The API/profile contract and real payload semantics were validated directly.
