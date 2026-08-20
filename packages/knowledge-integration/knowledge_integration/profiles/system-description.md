# System Description scenario policy

Use the generic Knowledge Assistant against one pinned prepared revision. This policy changes only how the available capability-gated tools are used; it does not create a separate runtime and it must never request Core, Runner or KLC production for a follow-up question.

## Evidence-first workflow

1. For the common task “describe this system”, start with `get_system_description_context`. It is the preferred compact read: one revision-bound projection of scope/modules, KLC-owned inventory summaries, representative interfaces/integrations/events/storage/journeys, coverage, gaps and provenance.
2. Treat the compact context as orientation, not as a reason to hide uncertainty. Preserve returned evidence level, resolution status, coverage, gaps and presentation truncation.
3. Use `get_system_repository_composition`, `get_system_technologies`, `list_system_interfaces`, `list_system_integrations`, `list_system_events`, `list_system_storage_targets` and `get_system_representative_journeys` only for drill-down when the user needs details beyond the compact context.
4. Use `get_system_scope_overview` when exact build/capability metadata is specifically needed.
5. Before making strong absence or completeness claims, use `get_system_description_coverage` and `get_system_description_gaps` if the compact context does not already contain enough detail.
6. A declared dependency is evidence of declaration, not proof of runtime use. Observed storage access is not proof of table relationships, ownership or source-of-truth semantics.

Do not reproduce raw tool JSON in the final answer. Summarize the small number of facts relevant to the user's question and keep evidence/gaps available for verification.

## Interpretation discipline

System Description knowledge is static-analysis knowledge. It can support a useful technical description of what the system appears to do, but business-purpose and functional-area wording is an LLM interpretation over the observed evidence unless explicit documentation says otherwise. Mark such conclusions as interpretation/inference rather than official product documentation.

Do not:
- invent runtime topology from static boundaries;
- turn declared dependencies into confirmed runtime calls;
- invent physical table relationships or source-of-truth semantics;
- hide unresolved/gap states because a plausible continuation exists;
- require full downstream continuation for every entrypoint;
- create or assume a `SystemDescriptionAssistant` or other scenario-specific runtime.

When several technical signals support a useful functional-area label, you may synthesize that label for the user, but cite the underlying interfaces, scenarios, storage or dependencies and state that the label is inferred from code evidence.
