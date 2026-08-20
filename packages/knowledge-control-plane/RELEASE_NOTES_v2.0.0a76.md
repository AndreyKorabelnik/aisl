# Analysis UI 2.0.0a76

Moves standard chat to one universal prepared-revision consumer path.

- `assistant_context` now binds exactly one primary Knowledge API revision; the legacy `attribute_addition` multi-revision kind and source/sql/PDM roles are removed.
- Assistant execution always uses `KnowledgeApiAssistantTools` over that pinned revision.
- Scenario behavior is optional and declarative through `ProfileInfo.assistant_profile_id`; generic profiles do not load the attribute-addition policy.
- Job publication copies the selected knowledge profile's optional Assistant policy ID into context metadata.
- Runtime dependency is updated to Knowledge Assistant 0.18.x.
- No Core/Runner/KLC production is triggered by chat questions.
