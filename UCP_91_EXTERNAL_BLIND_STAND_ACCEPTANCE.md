# UCP 91 external blind stand acceptance

Date: 2026-08-15  
Status: **UCP_91_EXTERNAL_BLIND_STAND_READY**

## Scope

Prepare a Gold-isolated, consumer-only acceptance stand for a genuinely independent external LLM run over the 91 UCP attributes. This block does **not** claim an external-agent score because no independent LLM connector is available in the execution environment.

## Observed acceptance facts

- Reused existing typed Core evidence; Core analyzer execution count for the fresh current materialization was **0**.
- Current Runner `0.10.25` executed exactly one node: `materialization:code-declared-data-model` using KLC `0.61.0a30`.
- Fresh result: `knowledge_execution_result/v2`, status `completed`.
- Result fingerprint: `34479d0fcad4a55991a267c7e3aa0f976e996eab369a20dd5a146fc16e8c63e7`.
- Result SHA-256: `6961883bfd7ecee2d19ae36a6d0a98e94cdebb5c26c370ebe8e3e5f2131287f9`.
- Knowledge artifact: `knowledge_artifact_1bb528e2ed90efc88f03` (`code-declared-data-model/v1`).
- Official Knowledge API publication produced `ucp-91-blind / rev-828b3d5897d6bf2f09d6b0c4`.
- Publishing the same execution result into a second empty catalog produced the **same revision id**.
- Generated consumer-kit fingerprint: `5ab7de36460ef6cc48e3ca494db8d8213e93780dc96f717c91d05f585b6ed865`.
- Capability-gated tool catalog contains exactly four tools: declared-model summary, lexical object/field search, exact declared object read and universal exact AISL item read.
- HTTP Knowledge API serve/read smoke: PASS.
- Pre-Gold result freeze validator accepts a structurally valid 91-item result and rejects a duplicate input index.
- Optional consumer-side OpenAI-compatible reference runner: dry-run PASS; generated tool binding → live Knowledge API summary call PASS.

## Blindness boundary

The portable stand contains the 91 inputs, output contract, consumer policy, prepared KnowledgeProduct, generated consumer-kit and publication/freeze tooling. It contains **no Manual Gold dataset, historical Gold result, or acceptance-only target map**.

The prepared AISL knowledge naturally contains technical FQCNs/fields; that is the information the consumer is supposed to query and is not Gold leakage.

## Interpretation

AISL/read reachability had already been established at 29/29 Gold-positive facts. This block only makes the external test operational and reproducible. The true agent recall/precision/confidence calibration remains **unresolved** until an independent LLM produces one frozen 91-item result without Gold exposure.

No framework runtime code changed in this block.
