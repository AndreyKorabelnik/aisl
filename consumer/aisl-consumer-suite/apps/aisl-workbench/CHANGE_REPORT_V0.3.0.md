# AISL Workbench 0.3.0 — External Agent / Chat integration

- Added Chat tab bound to the currently pinned immutable AISL revision.
- Added separate `AISL_AGENT_URL` proxy; no agent or LLM logic is embedded into the Workbench.
- Workbench creates an external agent session with explicit `system_id`, `revision_id`, and Consumer Profile id.
- Displays final answer plus exact tool calls/results returned by the external agent runtime.
- Switching/unpinning revision clears the agent session and chat history.
- Knowledge API proxy remains read-only; Chat does not route through KCP or mutate AISL.
