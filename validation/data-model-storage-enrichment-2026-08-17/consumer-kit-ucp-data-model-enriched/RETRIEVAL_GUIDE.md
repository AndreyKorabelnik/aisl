# Code-declared Data Model scenario policy

Use the generic Knowledge Assistant against one pinned prepared revision containing `code-declared-data-model` knowledge. The same policy applies whether that revision was produced from one repository or a workspace of several repositories. Never request Core, Runner or KLC production for a follow-up question.

## Evidence-first workflow

1. Start with the Integration Profile `scope`/`capabilities`, then `get_declared_data_model_summary` without semantic filters. Inspect repository scope, raw counts, observed type/field annotation frequencies and explicit gaps.
2. If the user asks for the system/domain model rather than every declared Java type, infer a semantic projection only from observed technical markers and documentation. Select exact marker names using `type_annotations`; if ignore/exclusion markers are explicitly observed and relevant, pass them through `exclude_field_annotations` to the summary. State the selected markers and why they are a strongly supported projection. Do not encode application-specific annotation names in the runtime or assume that every annotation has business semantics.
3. Use `search_declared_data_objects` with the same exact `type_annotations` projection when listing/searching model objects. Treat `search` as a lexical discovery term: prefer one short exact/technical token per call and issue alternative synonyms/translations as independent calls rather than concatenating many terms into one string. If the consumer runtime supports batching independent read calls, batching those short searches is preferred. Use `retrieval_score` only for deterministic candidate ordering; it is not semantic confidence. Read bounded `match_evidence` to see which observed type/field caused a hit and `binding_summary` to distinguish an observed bound type from a merely co-present dictionary/type. A short or business-facing name may return several grounded candidates: never select the first result mechanically. Compare FQCN, `repo_id`, match evidence, observed bindings, annotations/documentation and source path. If the projected search has insufficient evidence, explicitly repeat the strongest short search term with no `type_annotations` filter (`search_scope=all_declared_types`) before concluding `unresolved`; this is an observable scope expansion, never a silent fallback. If evidence still does not disambiguate candidates, preserve the ambiguity. For an exact type, prefer `get_data_model_object_context`: it returns the exact declared object plus any exact logical-storage/model-storage semantics already published in the pinned revision, with missing storage context explicit. Use `get_declared_data_object` only when the question is intentionally limited to declared-code structure. Preserve direct vs inherited fields, observed annotations, inheritance depth, incoming/outgoing binding summary, source repository and provenance.
4. Treat explicit ignore annotations as two simultaneous facts: the declaration exists in code, and the selected semantic projection may exclude it. Never erase the declaration from evidence.
5. Relationship `cardinality_hint` is KLC knowledge with an explicit `cardinality_basis`; preserve the basis. Inheritance and relationship resolution statuses remain visible.
6. For a multi-repository revision, distinguish facts by `repo_id`/source provenance. Do not interpret repository co-presence as ownership, duplication or a cross-repository relation unless the knowledge explicitly supports it.
7. Before claiming completeness, inspect gaps from the summary/detail. `partial` evidence does not make useful model knowledge unusable, but unresolved types/declarations must remain visible.

## Boundary discipline

The base product describes structure declared in source code. `get_data_model_object_context` may additionally expose exact storage semantics only when the selected revision already publishes the corresponding storage products. It does **not** by itself prove physical tables, columns, PK/FK constraints or SQL JOIN predicates. Never derive those facts from class/field names, declared relationships or storage aliases. If storage products are absent, preserve `not_available`; if physical SQL/PDM evidence is absent, preserve `physical_mapping.status=not_observed`.

A useful domain-model classification may be a strongly supported inference over observed code annotations/documentation. Label that inference and its basis; do not present it as a universal framework rule or official business taxonomy.

## Semantic confidence discipline

When using declared-model evidence for semantic matching, separate retrieval from meaning. Classify the evidence role before assigning confidence:

- `direct_field`: an observed field/documentation directly expresses the requested concept;
- `bound_type`: an observed relationship binds the candidate type/dictionary to the relevant owner object;
- `unbound_type`: the type/dictionary exists but no relevant observed binding is visible;
- `partial_component`: evidence covers only one component of a compound business attribute;
- `related_concept`: observed semantics are related but materially different;
- `generic_container`: the structure can store arbitrary facts/text but no observed producer/type/value proves this particular business concept;
- `no_candidate`: no supported candidate.

A generic container's capacity to store X is not observed evidence that X is stored there. A related-but-different concept is not a positive match. An unbound dictionary/type must not be promoted to a unique strong client-attribute match solely because its name is similar. For compound attributes preserve `covered_components`, `uncovered_components` and `match_scope=partial|complete`; one matching component does not prove the whole attribute.
