# knowledge-api 0.30.14

- Adds revision-bound `GET /systems/{system_id}/system-description/guidance`.
- The guidance endpoint is a bounded consumer projection over canonical KLC System Description queries.
- It preserves KLC-owned counts, evidence levels, coverage and gaps and does not infer business purpose, functional areas, runtime topology or storage semantics.
