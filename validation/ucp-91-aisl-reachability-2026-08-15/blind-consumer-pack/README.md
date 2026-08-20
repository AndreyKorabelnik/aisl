# UCP 91 — blind consumer pack

This directory is safe to give to an external consumer before evaluation. It intentionally contains no Manual Gold answers and no acceptance-only target map.

Use a pinned AISL system/revision containing the current UCP code-declared KnowledgeProduct. Generate/use the official consumer kit for that revision and follow `CONSUMER_POLICY.md` plus `EVALUATION_PROTOCOL.md`.

Files:

- `INPUTS_91.json` — only the 91 requested business attributes;
- `OUTPUT_SCHEMA.json` — result contract;
- `CONSUMER_POLICY.md` — current generic code-declared consumer policy;
- `EVALUATION_PROTOCOL.md` — isolation/freeze rules;
- `evaluate_91.py` — post-freeze structural comparison; it requires Gold as an explicit external argument.

Do not place Manual Gold in this directory before the agent run.
