# code-analyzer-core 0.44.8 — structured SQL script-call evidence

Publishes generic structured `sql_script_call` facts from observed orchestration/script statements.

Core records syntax and provenance only: call symbol, named/positional arguments and referenced placeholders. It does not assign persistence/materialization semantics and contains no datamart/UCP-specific call names or table rules.

Real datamart validation observed 412 structured script calls. This evidence is consumed downstream by KLC to derive script materialization only when bindings resolve uniquely.
