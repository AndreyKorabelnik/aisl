# knowledge-integration 0.1.12

Consumer ergonomics for `system-interactions/v1` profile v2.

- Adds capability-gated `get_system_interaction_context` bound to the compact exact System Interactions guidance endpoint.
- Common retrieval becomes `list_system_interactions → get_system_interaction_context` on one pinned revision.
- `list_interaction_boundaries` is explicitly retained as repository-boundary inventory, not as a reconstruction path for already-published matched interactions.
- Execution-context and field-contract list tools remain available for drill-down/continuation when the compact response reports truncation or a narrower filter is needed.
- No interaction confidence, matching, endpoint identity or field mapping is produced in the integration layer.
- Tool catalog contract version is now 5; profile version is 2.
