# Post-recovery merge — Slim Source JOIN v10

Date: 2026-08-14
Status: MERGED INTO CANONICAL SOURCE

## Input

- Recovery baseline: `repository-inventory-fi001-recovery-2026-08-13.zip`.
- Post-recovery distribution: `knowledge-consumer-bundle-slim-source-join-v10-2026-08-13.zip`.

## Exact runtime delta recovered from wheels

`prepared-knowledge-runtime 0.1.0.post4`: no source delta.

`knowledge-integration 0.1.2`:
- `knowledge_integration/profile_registry.py`: `attribute-addition-plan/v1` version 9 → 10.
- `knowledge_integration/profiles/attribute-addition-plan.md`: source-extraction JOIN/SQL retrieval and concise-answer policy.
- source package version 0.1.1 → 0.1.2.

`knowledge-api 0.30.6`:
- runtime code unchanged except `knowledge_api/version.py` version 0.30.5 → 0.30.6.
- source package dependency aligned to `knowledge-integration==0.1.2`.

## Architecture preserved

No Core, Runner, KLC, KCP, Prepared Knowledge contract, tool catalog, or capability-gating change was introduced by this merge.

The external LLM/agent remains responsible for the tool-calling loop. The generated Integration Profile / Consumer Kit is the contract that teaches the host/model which tools exist and how to call them. `external_consumer_http.py` remains a reference single-tool executor, not a dialogue runtime.

## Source JOIN behavior in profile v10

For requests such as obtaining an attribute from source tables, the profile now directs the consumer to:
1. do short object discovery with fields suppressed;
2. load the exact object and declared relationships;
3. identify the exact source field and minimum relationship path;
4. use `get_data_model_attribute_extension_context` when a relationship is involved;
5. find observed source SQL relations/joins with SQL tools;
6. use PDM only as structural confirmation when required;
7. emit a concise executable SELECT/JOIN and stop, without entering target-datamart ranking unless the user asked for a datamart change.

Declared relationship remains logical evidence and is never treated as sufficient proof of a physical SQL JOIN.
