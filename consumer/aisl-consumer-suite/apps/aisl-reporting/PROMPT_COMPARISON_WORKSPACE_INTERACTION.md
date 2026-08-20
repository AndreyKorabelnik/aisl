# Workspace interaction business report: comparison with llm-prompts 0.31.0

## Compared profiles

- Former reference: `workspace-system-interaction-business-report` from `llm-prompts 0.31.0`.
- Current profile: `workspace-interaction/v1` in `aisl-reporting 0.12.0`.

## Result

The current profile preserves the business-context-first composition of the former report and moves it to the canonical typed evidence available in `knowledge-layer-core 0.49.1`.

It does not retain the former analysis-bundle/final-response contract. Generic correspondences and data-model relationships are not used as runtime interactions.

## Composition parity

Both profiles require the following narrative order:

1. concise business conclusion;
2. business view of the workspace and interaction map;
3. system roles;
4. operation-centric interactions;
5. exchanged data groups;
6. architecture observations;
7. 2–5 attribute journeys as supporting examples;
8. questions for the agent;
9. open questions;
10. evidence quality and limitations;
11. technical appendix.

Attribute journeys remain supporting evidence and should occupy roughly 20–30% of the main narrative rather than becoming the report skeleton.

## Improvements over the former evidence contract

| Area | Former report input | Current deterministic input |
|---|---|---|
| Interaction identity | semantic analysis bundle and final response | canonical outbound-boundary → inbound-boundary facts |
| Operations | interpreted interaction findings | exact source/target operation identifiers, HTTP method and endpoints |
| Data exchange | attribute exchange candidates | typed system interaction field contracts |
| Attribute movement | mixed candidate histories | bounded resolver paths over local value-flow, serialization and transport edges |
| Execution context | often coupled to interaction discovery | explicitly optional local context; not a precondition for a boundary interaction |
| Confidence | report must preserve analysis status | `confirmed`, `probable`, `ambiguous`, `unresolved` preserved directly from KLC |
| Topology | report bundle view | repository interaction coverage and unmatched-operation diagnostics |
| Diagnostics | analysis warnings | unmatched/ambiguous outbound diagnostics and repository coverage |
| Provenance | analysis-bundle evidence references | repository-relative evidence index with no absolute runtime paths |

## Required safeguards retained

The current prompt explicitly forbids:

- inventing interactions, field contracts or missing path segments;
- treating generic build/type/configuration correspondences as runtime calls;
- promoting `probable` or `probable_complete` to confirmed;
- treating a technically complete path as proof of business identity, ownership or source of truth;
- declaring the absence of storage, Kafka, databases or downstream calls when the corresponding analysis was not run;
- exposing absolute runtime paths or internal tool commands;
- presenting diagnostic counts as precision percentages or business object counts.

## Real validation

The profile was prepared against the real two-repository workspace produced by the lightweight interaction-lineage suite:

- repositories: 2;
- canonical boundary interactions: 1;
- interaction confidence: `probable`;
- field contracts: 7;
- candidate transport edges: 7;
- selected attribute journeys: 5;
- unresolved outbound operations: 21;
- evidence entries: 12;
- absolute `/mnt/data` or `/home` paths in dataset: 0.

The prepared package contains operation-centric interaction details, nested field contracts (`phone.flags.*`) and bounded attribute paths. It does not contain legacy `cross_repository_correspondences` or `journey_candidates` sections.

## Known limitation

The report quality is bounded by the workspace analysis coverage. In the real validation case only one of twenty-two outbound operations was matched within the selected two-repository workspace. The prompt therefore requires the report to distinguish the one probable observed interaction from the twenty-one unresolved outbound boundaries instead of describing the workspace as a complete production topology.
