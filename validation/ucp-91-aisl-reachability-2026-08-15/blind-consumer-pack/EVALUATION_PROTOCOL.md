# Blind external-agent evaluation protocol — UCP 91 attributes

Purpose: measure the external consumer/agent against a pinned AISL revision without using Manual Gold as runtime input.

## Isolation rule

The consumer receives only:

- `INPUTS_91.json`;
- the pinned system/revision identifier;
- the generated AISL consumer kit / Integration Profile / tool catalog;
- read-only Knowledge API access.

Do **not** expose Manual Gold, the historical diff, Gold target FQCN/field names, or acceptance-only reachability files to the consumer before its output is frozen.

## Expected workflow

1. Read capabilities and declared-model summary first.
2. Derive a domain-model projection only from observed annotations/documentation.
3. Use short independent lexical searches and synonyms/translations. `retrieval_score` orders candidates; it is not semantic confidence.
4. Inspect `match_evidence`, `binding_summary`, FQCN, source path and documentation. Never pick rank #1 mechanically.
5. If projected search is insufficient, explicitly repeat the strongest query with `all_declared_types` scope.
6. Inspect the exact chosen object before answering.
7. Preserve `ambiguous` and `unresolved`. Generic containers, related concepts and unbound dictionaries are not direct matches.
8. For compound attributes, say which components are covered and which are not.

## Freeze and compare

Write one `ucp-attribute-agent-result/v1` JSON document matching `OUTPUT_SCHEMA.json`. Freeze its SHA-256 before opening Gold. Only then run the evaluator with Manual Gold as an acceptance-only input.

This protocol evaluates the agent as a consumer. It must not trigger Core/Runner/KLC production when the pinned AISL revision already contains the required knowledge.
