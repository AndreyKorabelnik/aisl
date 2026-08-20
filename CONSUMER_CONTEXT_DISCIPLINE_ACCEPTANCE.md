# Consumer context discipline — acceptance

Date: 2026-08-14

## Targeted tests

- knowledge-integration + knowledge-assistant + knowledge-chat backend: 88 PASS.
- One pre-existing FastAPI duplicate Operation ID warning in Chat proxy; no failure.
- compile/import for changed Python packages: PASS.
- full framework regression: NOT RUN (change is isolated to consumer boundary and Assistant runtime).

## Replay of supplied 10 trace files

Replay used the same raw ToolResponse payloads and the new model-facing projection; no LLM call was made.

- total original tool-result context: 2,655,251 chars
- projected tool-result context: 742,627 chars
- reduction: 72.0%

Heavy batches, predicted maximum request size after replacing raw tool messages with bounded views:

- batch 7: ~417,757 -> ~73,147 chars
- batch 8: ~716,155 -> ~121,007 chars
- batch 9: ~836,928 -> ~88,752 chars

Correctness checks from the same traces:

- batch 2: only one semantic search (`VIP`); runtime coverage therefore cannot support absence claims for the remaining requested items.
- batch 8: broad raw paging was truncated in LLM-visible projection; `full_model_scan_visible=false`.
- batch 10: 12 tool calls exhaust the budget; final synthesis receives `budget_exhausted=true` and must preserve an explicit coverage gap.

## Limitations

Actual wall-clock speedup is not claimed from replay alone. It depends on the external model implementation and must be measured by rerunning the 91-attribute scenario against the same revision/model.
