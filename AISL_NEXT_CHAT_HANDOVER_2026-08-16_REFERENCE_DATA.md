# AISL next-chat handover — Reference Data complete

Date: 2026-08-16  
Status: **REFERENCE_DATA_AISL_BLOCK_COMPLETE**

## Canonical continuation point

This recovery supersedes the previous System Description + FDP canonical only after the final ZIP/SHA values recorded in the recovery package are verified.

Completed product domains now include:

- System Description;
- Foreign Data Persistence / persistence lineage;
- System Interactions;
- Reference Data / NSI;
- declared/effective data-model and attribute-extension knowledge from prior blocks.

## Reference Data result

Real AT900 production path succeeded through the official AISL publication boundary:

`Core → Runner → KLC reference-data/v1 → knowledge_execution_result/v2 → Knowledge API → rev-7e8a9ec88020277028ac41cb`.

Frozen semantic acceptance remains stable:

- 7/7 strong;
- 4/4 borderline;
- 11/11 controls;
- 25/25 semantic-definition technical checks;
- 25/25 interpretation-policy guards.

No Core/Runner/KLC change was needed.

Consumer improvement:

- Knowledge API 0.30.16;
- Knowledge Integration 0.1.15;
- Reference Data profile v2;
- tool catalog v8;
- compact `get_reference_data_context`;
- global discovery approximately -96.7%, PRODUCT_PRICE -88.3%, operatorId -96.5% versus previous broad reads.

## Important semantic boundary

Reference Data runtime does not assign official enterprise NSI status/global authority. Local seed/code definitions are technical evidence. `operatorId` external ingress and local `MOBILEOPERATOR` dictionary evidence remain separate facts; their business relationship/ownership is not silently inferred.

## Next recommended step

Do not invent another Reference Data producer or continue architectural cleanup for its own sake.

Recommended immediate acceptance:

1. Run 2–3 real external-agent prompts against an already prepared Reference Data revision, for example:
   - “Какие собственные справочники вероятно есть в системе?”;
   - “Что известно про PRODUCT_PRICE?”;
   - “operatorId приходит извне или определяется системой, и как это соотносится с MOBILEOPERATOR?”
2. Evaluate tool choice, call count, answer compactness and preservation of confidence/authority boundaries.
3. Change consumer read/API again only if those traces prove a remaining friction.
4. Then choose the next knowledge domain by product value/Gold coverage. Do not automatically resume parked scope.

If a future multi-domain snapshot acceptance is performed, compose products only when system identity/official base revision semantics justify it. Do not merge unrelated systems merely to demonstrate composition.

## Parked scope remains parked

- UCP-91 independent blind external run;
- FI-002;
- vector/embedding retrieval inside AISL;
- portfolio topology;
- universal graph/EAV;
- agent memory/planning;
- compatibility cleanup without a proven active architectural duplicate.
